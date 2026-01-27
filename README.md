# azure-webhook-to-jira-updates

Webhook Python que recebe eventos do Azure DevOps relacionados a Pull Requests e adiciona/atualiza comentários nas tarefas do Jira correspondentes.

Os Pull Requests devem conter o ID da tarefa do Jira no título no formato `[J:CHAVE-123]`. O webhook acumula as atualizações de um mesmo PR em um único comentário no Jira, evitando spam.

Este projeto foi desenvolvido para funcionar com instâncias auto-hospedadas do Jira (Jira Server/Data Center).

## Instalação

1. Clone o repositório.
2. Crie um ambiente virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # No Windows: venv\Scripts\activate
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Configuração

1. Copie o arquivo de exemplo de configuração:
   ```bash
   cp .env.example .env
   ```
2. Edite o arquivo `.env` com as suas credenciais e URL do Jira:
   - `JIRA_URL`: URL base do seu Jira (ex: `https://jira.suaempresa.com.br`).
   - `JIRA_API_KEY`: Seu Personal Access Token (PAT) ou senha.
   - `JIRA_USERNAME`: Seu nome de usuário (necessário se estiver usando Autenticação Básica com senha; se usar apenas PAT como Bearer Token, pode deixar em branco ou ajustar o código conforme a configuração do seu servidor).

## Uso

Para rodar a aplicação:

```bash
sudo python3 app.py
```

**Nota:** Como a aplicação roda na porta 80, é necessário privilégios de administrador (root/sudo) em sistemas Linux/Unix.

## Configuração no Azure DevOps

1. Vá até o seu projeto no Azure DevOps.
2. Acesse **Project Settings** > **Service Hooks**.
3. Crie uma nova assinatura (**Create Subscription**) clicando no botão `+`.
4. Escolha o serviço **Web Hooks**.
5. Configure os seguintes eventos para a URL do seu webhook (ex: `http://seu-servidor/webhook`):
   - **Pull request created**
   - **Pull request merge attempted**
   - **Pull request updated**
   - **Pull request commented on**
6. Nos filtros, você pode especificar o repositório se desejar.
7. Teste a conexão para garantir que o Azure DevOps consegue alcançar seu servidor.

## Funcionamento

Quando um evento ocorre no Azure DevOps:
1. O webhook recebe o JSON.
2. Procura pelo padrão `[J:CHAVE-ID]` no título do Pull Request.
3. Se encontrado, busca na tarefa do Jira correspondente se já existe um comentário com o link daquele PR.
4. Se existir, adiciona a nova informação ao comentário existente.
5. Se não existir, cria um novo comentário.

As mensagens são geradas em Português do Brasil.
