# 🤖 Bot de Listas no Discord com Supabase

Este bot permite criar e gerenciar **listas colaborativas** em canais autorizados do Discord, com armazenamento persistente no **Supabase**. Ideal para listas de tarefas, materiais, itens de jogos ou qualquer organização em grupo.

## ✅ Funcionalidades

- Criar e editar listas de forma colaborativa via comandos.
- Atualização automática dos embeds (visual das listas).
- Permissões configuráveis por canal e cargo.
- Registro de ações via canal de log.

---

## 🚀 Como rodar o bot

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/seu-repositorio.git
cd seu-repositorio
```

### 2. Instale as dependências

Crie um ambiente virtual (opcional, mas recomendado):

```bash
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows
```

Depois instale:

```bash
pip install -r requirements.txt
```

### 3. Configure o `.env`

Crie um arquivo `.env` na raiz do projeto com as variáveis:

```env
DISCORD_TOKEN=seu_token_do_bot
DISCORD_APP_ID=seu_application_id
DISCORD_GUILD_ID=seu_guild_id
SUPABASE_URL=https://sua-instancia.supabase.co
SUPABASE_KEY=sua-chave-secreta
```

---

## 🧠 Como usar (passo a passo)

### 🛠️ 1. Configuração inicial (admin)

Use os comandos abaixo para configurar o bot no servidor (somente admins ou cargos permitidos):

| Comando                             | Descrição |
|------------------------------------|-----------|
| `/config adicionar_canal_lista`   | Autoriza um canal para usar listas. |
| `/config remover_canal_lista`     | Remove a autorização do canal. |
| `/config definir_canal_logs`      | Define onde logs de ações serão enviados. |
| `/config adicionar_cargo`         | Permite que um cargo use os comandos. |
| `/config remover_cargo`           | Revoga a permissão de um cargo. |
| `/config show`                    | Mostra todas as configurações atuais. |

### 📦 2. Gerenciamento de Listas

| Comando                  | Descrição |
|--------------------------|-----------|
| `/criar_lista nome`      | Cria uma lista com o nome informado. |
| `/adicionar_item`        | Adiciona um item com quantidade em uma lista. Se o item já existir, a quantidade será somada. |
| `/remover_item`          | Remove quantidade de um item. Se chegar a 0, o item é excluído. |
| `/remover_lista`         | Remove toda a lista e seus itens. |
| `/iniciar_listas`        | Reenvia todos os embeds (visuais) de lista. Use se o bot reiniciar ou os embeds sumirem. (Admin apenas) |

---

## 📁 Estrutura dos arquivos

- `bot.py`: Ponto de entrada principal do bot.
- `item_control.py`: Lógica dos comandos, interações e controle das listas.
- `supabase_client.py`: Inicializa a conexão com o Supabase.
- `requirements.txt`: Dependências do projeto.

---

## 💡 Dicas

- O bot atualiza os **embeds automaticamente** ao iniciar ou ao adicionar/remover itens.
- Se um canal ou embed for excluído manualmente, use `/iniciar_listas` para recriar tudo.
- É possível usar **autocomplete** nos campos `lista` e `item` para facilitar o uso.