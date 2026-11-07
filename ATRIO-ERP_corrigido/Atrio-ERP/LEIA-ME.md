# ÁTRIO — Gestão empresarial | Edição visual aprovada

Este projeto substitui a interface anterior. **Não existem logins falsos, empresas de demonstração nem vendas pré-carregadas.** O primeiro acesso cria sua empresa e seus registros reais no banco local. Todos os indicadores começam vazios até você cadastrar informações.

## 1. Abrir no Windows (mais fácil)

1. Extraia o ZIP em uma pasta, como `Desktop\atrio-erp`.
2. Abra `iniciar_windows.bat` com dois cliques (a primeira execução instala bibliotecas).
3. Abra **http://127.0.0.1:8000** no navegador.
4. Clique em **Começar agora**, crie a empresa, o usuário proprietário e uma senha de 12 ou mais caracteres.
5. Entre no painel e comece por **Estoque e produtos**.

Se o Windows não reconhecer `py`, abra o terminal (CMD) dentro da pasta e use:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

**Dica:** não abra `index.html` com duplo clique. Esta versão usa um servidor Python porque cadastro, login e dados funcionam de verdade. Abra a URL acima com o servidor ligado.

## 2. Arquivos

- `main.py`: API FastAPI e modelos de dados.
- `static/index.html`: site da marca e contato comercial.
- `static/entrar.html`: login com sessão no servidor.
- `static/cadastrar.html`: criação de empresa e proprietário.
- `static/painel.html`: 20 áreas de trabalho.
- `static/assets/site.css` / `site.js`: layout e interação do site público.
- `static/assets/app.css` / `app.js`: layout e operações do painel.
- `data/atrio.db`: banco local SQLite, criado automaticamente no primeiro uso (não é incluído no ZIP).
- `exportar_contatos.py`: gera CSV das mensagens registradas no formulário para o operador do servidor.
- `tests/test_core.py`: testes de autenticação, estoque, vendas e isolamento multiempresa.
- `docker-compose.yml`, `Dockerfile`: base de implantação com PostgreSQL (exige HTTPS na frente da aplicação).

## 3. O que já funciona de verdade

**Novidades desta edição:** painel com indicadores de faturamento anual, lucro bruto, despesas e comparação mensal; saudação conforme horário; data e hora na barra superior em telas grandes; atalhos de trabalho; pesquisa entre 20 áreas com Ctrl+K no Windows. A identidade segue a referência aprovada: grafite, papel e terracota.


- Cadastro inicial de empresas, identificação de proprietário, autenticação com senha Argon2 e sessão HTTP-only.
- Separação das consultas por organização; testes verificam que outra organização não acessa produtos e vendas.
- Cadastro e edição de produtos, SKU, custos, preços, marca, categoria e estoque mínimo. Cadastro de produtos agora permite informar estoque inicial por filial; produtos esgotados aparecem identificados (desabilitados) na seleção de vendas.
- Entrada e saída de produtos por unidade; rejeição de saldo negativo.
- Vendas com vários itens, baixa de estoque e criação de lançamento financeiro interno.
- Clientes e fornecedores: cadastro, consulta, edição e exportação CSV.
- Financeiro: receitas, despesas, pendências e confirmação de pagamentos informados.
- Filiais: cadastro e seleção por unidade; visão geral consolidada da empresa.
- Gráficos, indicadores, alertas de reposição e histórico de atividades a partir de registros persistidos.
- Cadastro simples e edição de solicitações de compra, funcionários, ordens de serviço, contratos, contas financeiras e chamados de suporte.
- Registro **manual** de dados de notas fiscais, sem emissão nem transmissão.
- Relatórios CSV e análises baseadas em regras explícitas (não é um LLM).
- Design responsivo com tema claro/escuro, menu móvel e formulários específicos por área.
- Contato comercial persistido no servidor; notificações por SMTP opcional.

## 4. O que NÃO está pronto para clientes pagantes

A aplicação é uma **base funcional para continuar o desenvolvimento e testes**, não um ERP completo e auditado para uso comercial. As principais entregas ainda necessárias são:

- 2FA, verificação de e-mail, recuperação de senha por e-mail, gerenciamento de usuários e papéis/permissões granulares.
- Compras recebidas com atualização transacional automática do estoque; devoluções, transferências, lotes, validade e inventário completo.
- PDV offline, fechamento de caixa, conciliação bancária e integração real com meios de pagamento.
- Importação/assinatura/transmissão fiscal NF-e, NFC-e, NFS-e; regras tributárias, DANFE/XML e processos fiscais certificados.
- Folha, ponto, encargos, DRE contábil e processos trabalhistas.
- Assinaturas e cobranças recorrentes, suporte com notificações externas.
- IA de linguagem, previsão estatística de demanda e permissões de acesso da IA.
- Upload de documentos, segurança e retenção de documentos reais, relatórios PDF e Excel XLSX.
- Backups automáticos testados, fila de tarefas, monitoramento, logs centralizados, recuperação de incidentes.
- Rate limiting distribuído, regras RLS no PostgreSQL, migrações versionadas, teste de carga, auditoria de segurança e revisão LGPD.

**Não conecte dados pessoais ou financeiros de clientes reais antes de concluir os controles legais, operacionais e de segurança.**

## 5. Para implantação com PostgreSQL

1. Crie um arquivo `.env` na raiz com `POSTGRES_PASSWORD=uma_senha_longa_e_unica`.
2. Execute `docker compose up --build -d`.
3. Publique o serviço **somente atrás de HTTPS** (Caddy/Nginx) com domínio, certificados e backups. O serviço fica limitado a `127.0.0.1:8000` no arquivo Compose.
4. O modo `APP_ENV=production` habilita cookies Secure. O login só funciona com HTTPS no navegador nesse modo.
5. Configure SMTP para enviar avisos das mensagens do formulário, ou execute `python exportar_contatos.py` para revisar os contatos registrados.

Não exponha diretamente as portas do banco nem do Uvicorn para a internet. Ajuste um proxy e um serviço de migrações antes do primeiro lançamento.

## 6. Testar

```bat
python -m pip install pytest httpx
python -m pytest -q tests/test_core.py
```

Testes automatizados básicos cobrem venda com baixa de estoque, saldo insuficiente, geração financeira, empresa isolada, proteção contra POST sem cabeçalho e sessão encerrada. A navegação visual das 20 páginas também foi verificada em revisão local.

## 7. Princípios do design

Criamos uma linguagem visual própria para Átrio: tipografia editorial com títulos em serifa, contraste entre grafite e papel, terracota como sinal de ação, tabelas de alta legibilidade e menus por contexto de trabalho. Sem fotos de bancos de imagem, clientes inventados, números fabricados ou botões que simulam pagamentos bancários.

As fontes Fraunces e DM Sans podem ser carregadas do Google Fonts; na ausência de internet, há fontes do sistema como alternativa.

## 8. Referência visual aprovada

Esta edição segue a imagem escolhida para o Átrio: menu lateral grafite, papel off-white, tipografia editorial com títulos serifados, tons terracota e telas focadas no trabalho. A página comercial é escura; as telas administrativas são claras, com tabelas legíveis. As imagens na pasta `preview` mostram o estilo da versão anterior usado como base; a edição atual acrescenta indicadores e atalhos.

### Busca rápida e atalhos

- No painel, use **Ctrl+K** para localizar qualquer uma das 20 áreas (em Mac, Cmd+K).
- Em **Visão geral**, há atalhos para produto, venda e financeiro.
- O comparativo mensal só mostra porcentagem quando existem vendas no mês anterior. Sem base, é exibido um traço: não geramos uma porcentagem enganosa.
- A instalação inicia **sem empresa de amostra, sem lançamentos e sem produtos fictícios**. Você cadastra os seus próprios registros.

### Limites de implantação

Não publique diretamente na internet nem venda como sistema fiscal pronto: esta edição é uma base funcional com design consolidado, não um ERP concluído em todos os 20 módulos. Consulte a seção 4 para ver integrações e recursos ainda pendentes. As imagens da pasta `preview` não fazem parte dos dados armazenados pelo sistema.

## Atualização: estoque e vendas (07/11/2026)

- **Vendas e pedidos / PDV:** os produtos ativos aparecem no seletor mesmo com zero unidades. Os sem estoque ficam desabilitados e sinalizados, em vez de desaparecer; os com estoque baixo mostram quantidade e alerta, e podem ser vendidos enquanto houver saldo.
- **Novo produto:** campo opcional "Quantidade inicial em estoque", associado à unidade em uso. Se o produto já existia, a quantidade continua sendo ajustada pelo botão **Movimentar** na área Estoque. O valor "Estoque mínimo" é somente um alerta, não o saldo disponível.
- **Notas fiscais:** linguagem revisada para explicitar que as notas cadastradas são documentos já existentes. Não há emissão/transmissão de notas; isso exige integração com os órgãos fiscais.

**Para atualizar a instalação que já tem registros:** feche o servidor e faça uma cópia de `data/atrio.db`. Substitua somente `main.py`, `static/assets/app.js` e `static/painel.html` pelos arquivos desta versão. Mantenha sua pasta `data` e seu `.env` originais. Inicie o servidor novamente e use Ctrl+F5 no navegador.
