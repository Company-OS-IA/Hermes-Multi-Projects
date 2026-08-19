# Hermes Multi-Projects

Plugin independente para operar os mesmos perfis Hermes em múltiplos projetos, sem duplicar agentes nem modificar o core.

## O que resolve

- mapeia origem de canal para `profile + project_slug`;
- injeta contexto de projeto em mensagens de canais roteados e em superfícies locais com projeto selecionado;
- usa `projects/<slug>/AGENTS.md`, `PROJECT.md` e `CONTEXT.md` como fontes canônicas;
- canais sem rota ficam em escopo `company`, sem acesso implícito a dados de projeto;
- provisiona e cadastra projetos pelo comando `/project create`;
- expõe a tool `project_context` para o agente consultar o contexto ativo.

> **Limite V1:** o Hermes atual não passa `session_id` ao handler de slash command de plugin. Em CLI/TUI, a seleção manual é persistida por **perfil**, não por sessão individual. Canais roteados têm escopo determinístico por mensagem.

## Pré-requisitos

- Hermes Agent com suporte a plugins;
- Python 3.10+ e PyYAML (dependência padrão do Hermes);
- um workspace gravável, por exemplo `/srv/company-os` ou `~/.hermes`.

## Instalação

Instale pelo gerenciador nativo do Hermes, sem tocar no core:

Para repositório privado, use a URL SSH já autorizada no host:

```bash
hermes plugins install git@github.com:Company-OS-IA/Hermes-Multi-Projects.git --enable
```

Para repositório público, o shorthand também funciona:

```bash
hermes plugins install Company-OS-IA/Hermes-Multi-Projects --enable
```

Para atualizar depois:

```bash
hermes plugins update hermes-multi-projects
```

O plugin é instalado em `$HERMES_HOME/plugins/hermes-multi-projects/`.

## Configuração

```yaml
plugins:
  enabled:
    - hermes-multi-projects
  entries:
    hermes-multi-projects:
      workspace_root: ~/.hermes
      manifest: ~/.hermes/projects.yaml
      admin_profiles: [default]
```

| Campo | Descrição | Default |
|-------|-----------|---------|
| `workspace_root` | Raiz do workspace de projetos | `$HERMES_HOME` ou `~/.hermes` |
| `manifest` | Caminho do manifesto YAML | `<workspace_root>/projects.yaml` |
| `admin_profiles` | Perfis que podem criar/editar projetos | `[default]` |

Reinicie o gateway após habilitar ou atualizar o plugin.

## Começo rápido

### 1. Inicialize o Project OS uma vez

No chat do agente principal, fora de um canal já roteado para projeto:

```text
/project init
```

Isso cria apenas o manifesto vazio:

```text
~/.hermes/projects.yaml
```

Não cria nenhum projeto ainda.

### 2. Crie o primeiro projeto

```text
/project create pixel-x | Pixel X
/project create Pixel X
```

Ou, se o nome for omitido, o slug vira um título legível:

```text
/project create arquitetando-viagens
```

O comando cria e cadastra, de forma única, esta estrutura:

```text
projects/<slug>/
├── PROJECT.md
├── CONTEXT.md
├── AGENTS.md
├── knowledge/
├── operations/
│   ├── decisions/
│   ├── pending/
│   ├── risks/
│   └── reports/
├── artifacts/
├── checkpoints/
│   ├── project/
│   └── agents/
└── graph/
```

O projeto entra no manifesto inicialmente sem perfis nem rotas. Isto é intencional: **criar um diretório não concede acesso a nenhum agente**.

### 3. Autorize agentes e configure rotas

```text
/project add profile pixel-x-app pedro
/project add profile pixel-x-app david

/project add route pixel-x-app telegram -1000000000001 7 pedro
/project add route pixel-x-app telegram -1000000000001 - david
```

Uma rota é válida somente se seu `profile` também estiver em `profiles`. `/project add route` exige essa autorização, rejeita rotas duplicadas e usa `-` quando o canal não possui `thread_id`.

### 4. Reinicie e valide no canal

Após reiniciar o gateway, uma mensagem no grupo/tópico roteado recebe automaticamente o contexto correto:

```text
plataforma + chat_id + thread_id + perfil → projeto
```

## Comandos

```text
/project                                    mostra contexto atual
/projects                                   lista projetos autorizados ao perfil
/project init                               cria manifesto global vazio (admin)
/project create <slug> | <nome>             cria diretório e cadastra projeto (admin)
/project delete <slug>                      deleta projeto e seu diretório (admin)
/project rename <slug> <novo-nome>          renomeia o projeto (admin)
/project add profile <slug> <perfil>         autoriza perfil no projeto (admin)
/project add route <slug> <plataforma> <chat_id> <thread_id|-> <perfil>
                                             cadastra rota estável (admin)
/project use <slug>                         seleciona projeto fora de canal roteado
/project use company                        volta ao escopo organizacional
```

Em canal roteado, a rota é a autoridade: `/project use`, `/project init`, `/project create`, `/project delete` e `/project rename` ficam bloqueados.

## Manifesto de exemplo

```yaml
version: 1
projects:
  - slug: pixel-x
    name: Pixel X
    enabled: true
    profiles:
      - pedro
      - david
    routes:
      - platform: telegram
        chat_id: "-1000000000001"
        thread_id: "7"
        profile: pedro
      - platform: telegram
        chat_id: "-1000000000001"
        thread_id: ""
        profile: david

  - slug: arquitetando-viagens
    name: Arquitetando Viagens
    enabled: true
    profiles:
      - maria
    routes:
      - platform: telegram
        chat_id: "-1000000000002"
        thread_id: ""
        profile: maria
```

## Operação fora do Telegram

Em CLI, TUI, Dashboard e outras superfícies sem rota de canal, selecione o contexto antes do trabalho:

```text
/project use pixel-x
```

Depois confira:

```text
/project
```

Para sair do projeto:

```text
/project use company
```

## Segurança e limites

- O plugin oferece isolamento de contexto e validação de rotas; não é sandbox de sistema operacional.
- Ele não cria, copia nem gere credenciais.
- Contexto de projeto não deve ser promovido à memória do agente sem decisão explícita.
- Canais sem rota operam somente no escopo `company`; dados de projeto só entram por rota válida ou seleção manual autorizada.
- Fontes externas e informa��ões temporais precisam ser revalidadas.

## Troubleshooting

| Sintoma | Causa | Solução |
|---------|-------|---------|
| `Project OS não inicializada` | Manifesto não existe | Execute `/project init` |
| `Projeto não existe ou não está habilitado` | Slug errado ou perfil não autorizado | Verifique com `/projects` e `/project add profile` |
| `Este canal é roteado para projeto` | Tentou executar comando admin em canal roteado | Execute fora do canal roteado |
| `Perfil não autorizado` | Seu perfil não está em `admin_profiles` | Adicione seu perfil em `admin_profiles` no config |
| `CONTEXTO BLOQUEADO` | Faltam arquivos no projeto | Verifique `PROJECT.md`, `CONTEXT.md`, `AGENTS.md` |
| `Rota já existe` | Tentou cadastrar rota duplicada | Use `/project add route` com parâmetros diferentes |
| Plugin não aparece | Não está em `plugins.enabled` | Adicione `hermes-multi-projects` em `plugins.enabled` |
| `workspace_root` aponta para lugar errado | Config não definido | Defina `workspace_root` explicitamente no config |

## Desenvolvimento

```bash
python -m unittest discover -v
python -m py_compile __init__.py scripts/project_os.py scripts/install.py
```

O GitHub Actions executa os mesmos testes.
