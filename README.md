# azure-webhook-to-jira-updates
Webhook que recebe eventos do azure devops relacionados a pull requests e adiciona comentarios nas tarefas do Jira relacionados.
Webhook python que recebe eventos do azure devops relacionados a pull requests e adiciona comentarios nas tarefas do Jira relacionados.
Os pull requests são padronizados com os nomes das tarefas no título nesse formato: [J:XXXXXXXX] onde os X representam um numero de task do jira. 
O jira é auto hospedado e não é o em cloud da atlassian. 
