import discord
from discord.ext import commands
from discord import app_commands
from supabase_client import supabase
from discord.errors import Forbidden, NotFound


class ItemControl(commands.Cog):
    """Cog para gerenciamento de listas no Supabase, com permissões,
       logs, embed atualizado, autocomplete e inicialização automática."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._initialized = False
        bot.loop.create_task(self._auto_initialize())


    async def _safe_get_channel(self, cid: int):
        try:
            return self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
        except (Forbidden, NotFound):
            return None

    async def _safe_get_message(self, channel: discord.TextChannel, mid: int):
        try:
            return await channel.fetch_message(mid)
        except (Forbidden, NotFound):
            return None


    async def _auto_initialize(self):
        await self.bot.wait_until_ready()
        if not self._initialized:
            await self._reenvia_todas_listas()
            self._initialized = True

    async def _reenvia_todas_listas(self):
        total = 0
        for guild in self.bot.guilds:
            guild_id = guild.id
            for row in supabase.table("lists")\
                               .select("channel_id, list_name, message_id")\
                               .eq("guild_id", guild_id)\
                               .execute().data or []:
                channel_id = row["channel_id"]
                nome = row["list_name"]
                msg_id = row.get("message_id") or 0

                itens = supabase.table("items")\
                                .select("item_id, name, qty")\
                                .match({
                                    "guild_id": guild_id,
                                    "channel_id": channel_id,
                                    "list_name": nome
                                })\
                                .execute().data or []

                desc = "\n".join(
                    f"`[{i['item_id']}]` {i['name']} — {i['qty']}"
                    for i in itens
                ) or "Sem itens."
                embed = discord.Embed(
                    title=f"Lista: {nome}",
                    description=desc,
                    color=discord.Color.blurple()
                )
                embed.set_footer(text="Use /adicionar_item, /remover_item ou /remover_lista aqui.")

                channel = await self._safe_get_channel(channel_id)  
                if channel is None:
                    # limpa registros zumbi opcionalmente
                    supabase.table("lists").delete().match({
                        "guild_id": guild_id,
                        "channel_id": channel_id
                    }).execute()
                    continue              
                if msg_id:
                    msg = await self._safe_get_message(channel, msg_id)
                    if msg:
                        await msg.edit(embed=embed)
                        total += 1
                        continue

                msg = await channel.send(embed=embed)
                supabase.table("lists")\
                        .update({"message_id": msg.id})\
                        .match({
                            "guild_id": guild_id,
                            "channel_id": channel_id,
                            "list_name": nome
                        }).execute()

    def _get_settings(self, guild_id: int) -> dict:
        data = supabase.table("settings")\
                       .select("log_channel_id")\
                       .eq("guild_id", guild_id)\
                       .execute().data or []
        return data[0] if data else {}

    def _get_allowed_roles(self, guild_id: int) -> set[int]:
        return {
            r["role_id"]
            for r in supabase.table("allowed_roles")\
                         .select("role_id")\
                         .eq("guild_id", guild_id)\
                         .execute().data or []
        }

    def _get_list_channels(self, guild_id: int) -> set[int]:
        return {
            r["channel_id"]
            for r in supabase.table("list_channels")\
                         .select("channel_id")\
                         .eq("guild_id", guild_id)\
                         .execute().data or []
        }

    def _check_permission(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        user = interaction.user
        allowed = self._get_allowed_roles(guild_id)
        if not (user.guild_permissions.administrator or any(r.id in allowed for r in user.roles)):
            raise app_commands.MissingPermissions(
                ["use_application_commands"],
                message="Você não tem permissão para usar este comando."
            )

    def _ensure_list_channel(self, interaction: discord.Interaction):
        if interaction.channel.id not in self._get_list_channels(interaction.guild.id):
            raise app_commands.AppCommandError(
                "❌ Este canal não está autorizado para uso de listas."
            )

    async def _log(self, guild_id: int, content: str = None, embed: discord.Embed = None):
        log_chan_id = self._get_settings(guild_id).get("log_channel_id")
        if not log_chan_id:
            return
        try:
            channel = self.bot.get_channel(log_chan_id) or await self.bot.fetch_channel(log_chan_id)
            await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            return
        except Exception as e:
            print(f"Erro ao enviar log no canal {log_chan_id}: {e}")

    config = app_commands.Group(name="config", description="Comandos de configuração do bot")

    @config.command(name="show", description="Mostra as configurações atuais do bot")
    async def config_show(self, interaction: discord.Interaction):
        self._check_permission(interaction)
        cfg = self._get_settings(interaction.guild.id)
        allowed_roles = self._get_allowed_roles(interaction.guild.id)
        list_channels = self._get_list_channels(interaction.guild.id)
        embed = discord.Embed(title="Configurações do Bot", color=discord.Color.blue())

        canais = ", ".join(f"<#{cid}>" for cid in list_channels) if list_channels else "Nenhum"
        embed.add_field(name="Canais de Listas", value=canais, inline=False)

        log_chan = cfg.get("log_channel_id")
        embed.add_field(
            name="Canal de Logs",
            value=f"<#{log_chan}>" if log_chan else "Não definido",
            inline=False
        )

        roles = ", ".join(f"<@&{rid}>" for rid in allowed_roles) or "Nenhum"
        embed.add_field(name="Cargos Permitidos", value=roles, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config.command(name="adicionar_canal_lista", description="Autoriza um canal para usar listas")
    @app_commands.describe(canal="Canal a autorizar")
    async def config_add_list_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        self._check_permission(interaction)
        supabase.table("list_channels")\
                .insert({"guild_id": interaction.guild.id, "channel_id": canal.id}, upsert=True)\
                .execute()
        await interaction.response.send_message(f"✅ Canal {canal.mention} autorizado para listas.", ephemeral=True)
        await self._log(
            interaction.guild.id,
            content=f"🔧 Canal autorizado para listas: {canal.mention} por {interaction.user.mention}"
        )

    @config.command(name="remover_canal_lista", description="Revoga permissão de canal para listas")
    @app_commands.describe(canal="Canal a revogar")
    async def config_remove_list_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        self._check_permission(interaction)
        supabase.table("list_channels")\
                .delete()\
                .match({"guild_id": interaction.guild.id, "channel_id": canal.id})\
                .execute()
        await interaction.response.send_message(f"❌ Canal {canal.mention} removido das listas.", ephemeral=True)
        await self._log(
            interaction.guild.id,
            content=f"🔧 Canal removido das listas: {canal.mention} por {interaction.user.mention}"
        )

    @config.command(name="definir_canal_logs", description="Define o canal para logs do bot")
    @app_commands.describe(canal="Canal de logs")
    async def config_definir_logs(self, interaction: discord.Interaction, canal: discord.TextChannel):
        self._check_permission(interaction)
        supabase.table("settings")\
                .upsert({"guild_id": interaction.guild.id, "log_channel_id": canal.id})\
                .execute()
        await interaction.response.send_message(f"✅ Canal de logs definido: {canal.mention}", ephemeral=True)
        await self._log(
            interaction.guild.id,
            content=f"🔧 Canal de logs definido: {canal.mention} por {interaction.user.mention}"
        )

    @config.command(name="adicionar_cargo", description="Adiciona cargo permitido para usar comandos")
    @app_commands.describe(cargo="Cargo a permitir")
    async def config_add_role(self, interaction: discord.Interaction, cargo: discord.Role):
        self._check_permission(interaction)
        supabase.table("allowed_roles")\
                .insert({"guild_id": interaction.guild.id, "role_id": cargo.id}, upsert=True)\
                .execute()
        await interaction.response.send_message(f"✅ Cargo {cargo.mention} permitido", ephemeral=True)
        await self._log(
            interaction.guild.id,
            content=f"🔧 Cargo permitido adicionado: {cargo.mention} por {interaction.user.mention}"
        )

    @config.command(name="remover_cargo", description="Remove cargo permitido")
    @app_commands.describe(cargo="Cargo a remover")
    async def config_remove_role(self, interaction: discord.Interaction, cargo: discord.Role):
        self._check_permission(interaction)
        supabase.table("allowed_roles")\
                .delete()\
                .match({"guild_id": interaction.guild.id, "role_id": cargo.id})\
                .execute()
        await interaction.response.send_message(f"❌ Cargo {cargo.mention} removido", ephemeral=True)
        await self._log(
            interaction.guild.id,
            content=f"🔧 Cargo permitido removido: {cargo.mention} por {interaction.user.mention}"
        )

    @app_commands.command(name="criar_lista", description="Cria nova lista (ou mostra a existente)")
    @app_commands.describe(nome="Nome da lista")
    async def criar_lista(self, interaction: discord.Interaction, nome: str):
        self._check_permission(interaction)
        self._ensure_list_channel(interaction)

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        resp = supabase.table("lists")\
                       .select("message_id")\
                       .match({
                           "guild_id": guild_id,
                           "channel_id": channel_id,
                           "list_name": nome
                       })\
                       .execute()
        if resp.data and resp.data[0].get("message_id"):
            msg = await self._safe_get_message(interaction.channel, resp.data[0]["message_id"])
            if msg:  # embed ainda existe
                return await interaction.response.send_message(embed=msg.embeds[0], ephemeral=True)

        supabase.table("lists")\
                .upsert({
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "list_name": nome,
                    "id_counter": 0,
                    "message_id": 0
                })\
                .execute()

        embed = discord.Embed(
            title=f"Lista: {nome}",
            description="Sem itens.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Use /adicionar_item, /remover_item ou /remover_lista aqui.")
        msg = await interaction.channel.send(embed=embed)

        supabase.table("lists")\
                .update({"message_id": msg.id})\
                .match({
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "list_name": nome
                })\
                .execute()

        await interaction.response.send_message(
            f"✅ Lista **{nome}** criada neste canal.", ephemeral=True
        )
        await self._log(
            guild_id,
            content=f"✅ Lista **{nome}** criada em <#{channel_id}> por {interaction.user.mention}"
        )

    @app_commands.command(name="adicionar_item", description="Adiciona item na lista")
    @app_commands.describe(lista="Nome da lista", item="Nome do item", quantidade="Quantidade")
    async def adicionar_item(self, interaction: discord.Interaction, lista: str, item: str, quantidade: int = 1):
        self._check_permission(interaction)
        self._ensure_list_channel(interaction)

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        list_row = supabase.table("lists")\
                            .select("message_id")\
                            .match({
                                "guild_id": guild_id,
                                "channel_id": channel_id,
                                "list_name": lista
                            })\
                            .execute().data
        msg_id = list_row[0].get("message_id") if list_row else None

        existente = supabase.table("items")\
                            .select("item_id, qty")\
                            .match({
                                "guild_id": guild_id,
                                "channel_id": channel_id,
                                "list_name": lista,
                                "name": item
                            })\
                            .execute().data or []

        if existente:
            item_id = existente[0]["item_id"]
            nova_qty = existente[0]["qty"] + quantidade
            supabase.table("items")\
                    .update({"qty": nova_qty})\
                    .match({
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": lista,
                        "item_id": item_id
                    })\
                    .execute()
        else:
            resp = supabase.table("lists")\
                           .select("id_counter")\
                           .match({
                               "guild_id": guild_id,
                               "channel_id": channel_id,
                               "list_name": lista
                           })\
                           .execute().data
            if not resp:
                return await interaction.response.send_message(
                    f"⚠️ Lista **{lista}** não existe.", ephemeral=True
                )

            current = resp[0]["id_counter"] or 0
            next_id = current + 1

            supabase.table("lists")\
                    .update({"id_counter": next_id})\
                    .match({  
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": lista
                    })\
                    .execute()

            supabase.table("items")\
                    .insert({
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": lista,
                        "item_id": next_id,
                        "name": item,
                        "qty": quantidade
                    })\
                    .execute()
            item_id = next_id

        itens = supabase.table("items")\
                        .select("item_id,name,qty")\
                        .match({
                            "guild_id": guild_id,
                            "channel_id": channel_id,
                            "list_name": lista
                        })\
                        .execute().data or []

        desc = "\n".join(f"`[{i['item_id']}]` {i['name']} — {i['qty']}" for i in itens) or "Sem itens."
        embed = discord.Embed(title=f"Lista: {lista}", description=desc, color=discord.Color.green())
        embed.set_footer(text="Use /remover_item ou /remover_lista para modificar.")
        msg = await self._safe_get_message(interaction.channel, msg_id)
        if msg:
            await msg.edit(embed=embed)
        else:
            msg = await interaction.channel.send(embed=embed)
            supabase.table("lists").update({"message_id": msg.id}).match({
                "guild_id": guild_id,
                "channel_id": channel_id,
                "list_name": lista,
            }).execute()

        await interaction.response.send_message(
            f"🟢 {interaction.user.mention} adicionou {quantidade}x **{item}** na lista **{lista}**."
        )
        await self._log(
            guild_id,
            content=f"🟢 {interaction.user.mention} adicionou {quantidade}x **{item}** na lista **{lista}**."
        )

    @adicionar_item.autocomplete('lista')
    async def lista_autocomplete_adicionar(self, interaction: discord.Interaction, current: str):
        rows = supabase.table("lists")\
                       .select("list_name")\
                       .match({
                           "guild_id": interaction.guild.id,
                           "channel_id": interaction.channel.id
                       })\
                       .execute().data or []
        return [
            app_commands.Choice(name=r["list_name"], value=r["list_name"])
            for r in rows if current.lower() in r["list_name"].lower()
        ][:25]  

    @adicionar_item.autocomplete('item')
    async def item_autocomplete_adicionar(self, interaction: discord.Interaction, current: str):
        lista = interaction.namespace.lista
        rows = supabase.table("items")\
                       .select("name")\
                       .match({
                           "guild_id": interaction.guild.id,
                           "channel_id": interaction.channel.id,
                           "list_name": lista
                       })\
                       .execute().data or []
        nomes = sorted({r["name"] for r in rows})
        return [
            app_commands.Choice(name=n, value=n)
            for n in nomes if current.lower() in n.lower()
        ][:25]

    @app_commands.command(name="remover_item", description="Remove item da lista")
    @app_commands.describe(lista="Nome da lista", item="Nome do item", quantidade="Quantidade")
    async def remover_item(self, interaction: discord.Interaction, lista: str, item: str, quantidade: int = 1):
        self._check_permission(interaction)
        self._ensure_list_channel(interaction)

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        resp = supabase.table("items")\
                       .select("qty,item_id")\
                       .match({
                           "guild_id": guild_id,
                           "channel_id": channel_id,
                           "list_name": lista,
                           "name": item
                       })\
                       .execute()
        if not resp.data:
            return await interaction.response.send_message(
                f"⚠️ Item **{item}** não encontrado na lista **{lista}**."
            )

        original = resp.data[0]["qty"]
        item_id  = resp.data[0]["item_id"]

        if quantidade >= original:
            supabase.table("items")\
                    .delete()\
                    .match({
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": lista,
                        "item_id": item_id
                    })\
                    .execute()
        else:
            supabase.table("items")\
                    .update({"qty": original - quantidade})\
                    .match({
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": lista,
                        "item_id": item_id
                    })\
                    .execute()

        itens = supabase.table("items")\
                        .select("item_id,name,qty")\
                        .match({
                            "guild_id": guild_id,
                            "channel_id": channel_id,
                            "list_name": lista
                        })\
                        .execute().data or []

        desc = "\n".join(f"`[{i['item_id']}]` {i['name']} — {i['qty']}" for i in itens) or "Sem itens."
        embed = discord.Embed(title=f"Lista: {lista}", description=desc, color=discord.Color.red())
        embed.set_footer(text="Use /adicionar_item ou /remover_item para modificar.")
        msg_id = supabase.table("lists")\
                        .select("message_id")\
                        .match({
                            "guild_id": guild_id,
                            "channel_id": channel_id,
                            "list_name": lista
                        })\
                        .execute().data[0]["message_id"]
        msg = await self._safe_get_message(interaction.channel, msg_id)
        if msg:
            await msg.edit(embed=embed)
        else:
            msg = await interaction.channel.send(embed=embed)
            supabase.table("lists").update({"message_id": msg.id}).match({
                "guild_id": guild_id,
                "channel_id": channel_id,
                "list_name": lista,
            }).execute()
        

        await interaction.response.send_message(
            f"🔴 {interaction.user.mention} removeu {quantidade}x **{item}** da lista **{lista}**."
        )
        await self._log(
            guild_id,
            content=f"🔴 {interaction.user.mention} removeu {quantidade}x **{item}** na lista **{lista}**."
        )

    @remover_item.autocomplete('lista')
    async def lista_autocomplete_remover(self, interaction: discord.Interaction, current: str):
        rows = supabase.table("lists")\
                       .select("list_name")\
                       .match({
                           "guild_id": interaction.guild.id,
                           "channel_id": interaction.channel.id
                       })\
                       .execute().data or []
        return [
            app_commands.Choice(name=r["list_name"], value=r["list_name"])
            for r in rows if current.lower() in r["list_name"].lower()
        ][:25]

    @remover_item.autocomplete('item')
    async def item_autocomplete_remover(self, interaction: discord.Interaction, current: str):
        lista = interaction.namespace.lista
        rows = supabase.table("items")\
                       .select("name")\
                       .match({
                           "guild_id": interaction.guild.id,
                           "channel_id": interaction.channel.id,
                           "list_name": lista
                       })\
                       .execute().data or []
        nomes = sorted({r["name"] for r in rows})
        return [
            app_commands.Choice(name=n, value=n)
            for n in nomes if current.lower() in n.lower()
        ][:25]

    @app_commands.command(name="remover_lista", description="Remove toda uma lista e seus itens")
    @app_commands.describe(nome="Nome da lista a remover")
    async def remover_lista(self, interaction: discord.Interaction, nome: str):
        self._check_permission(interaction)
        self._ensure_list_channel(interaction)

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        supabase.table("items")\
                .delete()\
                .match({
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "list_name": nome
                })\
                .execute()

        resp = supabase.table("lists")\
                       .select("message_id")\
                       .match({
                           "guild_id": guild_id,
                           "channel_id": channel_id,
                           "list_name": nome
                       })\
                       .execute()
        msg_id = resp.data[0].get("message_id") if resp.data else None

        supabase.table("lists")\
                .delete()\
                .match({
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "list_name": nome
                })\
                .execute()

        channel = self.bot.get_channel(channel_id)
        if msg_id:
            try:
                msg = await self._safe_get_message(channel, msg_id)
                await msg.delete()
            except discord.NotFound:
                pass

        await channel.send(f"🗑️ Lista **{nome}** e todos os seus itens foram removidos.")
        await self._log(
            guild_id,
            content=f"🗑️ Lista **{nome}** e todos os seus itens removidos por {interaction.user.mention}"
        )

    @app_commands.command(name="iniciar_listas", description="(Re)publica todos os embeds de lista")
    @app_commands.checks.has_permissions(administrator=True)
    async def iniciar_listas(self, interaction: discord.Interaction):
        self._check_permission(interaction)
        guild_id = interaction.guild.id
        await interaction.response.defer()
        total = 0
        for row in supabase.table("lists")\
                           .select("channel_id,list_name,message_id")\
                           .eq("guild_id", guild_id)\
                           .execute().data or []:
            channel_id, nome, msg_id = row["channel_id"], row["list_name"], row.get("message_id") or 0

            itens = supabase.table("items")\
                            .select("item_id,name,qty")\
                            .match({
                                "guild_id": guild_id,
                                "channel_id": channel_id,
                                "list_name": nome
                            })\
                            .execute().data or []

            desc = "\n".join(f"`[{i['item_id']}]` {i['name']} — {i['qty']}" for i in itens) or "Sem itens."
            embed = discord.Embed(title=f"Lista: {nome}", description=desc, color=discord.Color.blurple())
            embed.set_footer(text="Use /adicionar_item, /remover_item ou /remover_lista aqui.")

            channel = await self._safe_get_channel(channel_id) 

            if channel is None:
                supabase.table("lists").delete().match({
                    "guild_id": guild_id,
                    "channel_id": channel_id
                }).execute()
                supabase.table("list_channels").delete().match({
                    "guild_id": guild_id,
                    "channel_id": channel_id
                }).execute()
                continue
           
            if msg_id:
                try:
                    msg = await self._safe_get_message(channel, msg_id)
                    if msg:
                        await msg.edit(embed=embed)
                        total += 1
                        continue
                except Exception:
                    pass

            msg = await channel.send(embed=embed)
            supabase.table("lists")\
                    .update({"message_id": msg.id})\
                    .match({
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "list_name": nome
                    })\
                    .execute()
            total += 1

        await interaction.followup.send(f"✅ Inicializadas {total} listas deste servidor.")
        await self._log(
            guild_id,
            content=f"✅ (Re)publicadas {total} listas por {interaction.user.mention}"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(ItemControl(bot))
