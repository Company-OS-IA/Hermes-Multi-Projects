# Hermes Multi-Projects

Plugin independente para operar os mesmos perfis Hermes em múltiplos projetos, sem duplicar agentes nem modificar o core.

## O que resolve

- mapeia origem de canal para `profile + project_slug`;
- injeta contexto de projeto em mensagens de canais roteados e em superfícies locais com projeto selecionado;
- usa `projects/<slug>/AGENTS.md`, `PROJECT.md` e `CONTEXT.md` como fontes canônicas;
- bloqueia canais não provisionados quando configurado em modo fechado;
- permite selecionar `company` ou um projeto fora de canais, por perfil;
- provisiona e cadastra projetos pelo comando `/project create`;
- expõe a tool `project_context` para o agente consultar o contexto ativo.

> **Limite V1:** o Hermes atual não passa `session_id` ao handler de slash command de plugin. Em CLI/TUI, a seleção manual é persistida por **perfil**, não por sessão individual. Canais roteados têm escopo determinístico por mensagem.

## Pré-requisitos

- Hermes Agent com suporte a plugins;
- Python 3.10+ e PyYAML (dependência padrão do Hermes);
- um workspace gravável, por exemplo `/srv/company-os` ou `/root/hermes-workspace`.

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

```yaml
plugins:
  enabled:
    - hermes-multi-projects
  entries:
    hermes-multi-projects:
      workspace_root: /root/hermes-workspace
      manifest: /root/hermes-workspace/projects.yaml
      fail_closed_gateway: true
      admin_profiles: [default]
```

`admin_profiles` controla quem pode executar `/project init` e `/project create`. Aceita um perfil único (`default`) ou uma lista (`[default, coo]`); por padrão, somente `default` (agente principal) pode provisionar projetos.

Reinicie o gateway após habilitar ou atualizar o plugin.

## Começo rápido

### 1. Inicialize o Project OS uma vez

No chat do agente principal, fora de um canal já roteado para projeto:

```text
/project init
```

Isso cria apenas o manifesto vazio:

```text
/root/hermes-workspace/projects.yaml
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

Edite o manifesto com os perfis e as rotas reais da sua instalação, depois valide:

```yaml
version: 1
projects:
  - slug: pixel-x
    name: Pixel X
    enabled: true
    profiles: [david, maya, pedro]
    routes:
      - platform: telegram
        chat_id: "-1000000000001"
        thread_id: "7"
        profile: pedro
```

```bash
python "$HERMES_HOME/plugins/hermes-multi-projects/scripts/project_os.py" validate \
  --workspace /root/hermes-workspace \
  --manifest /root/hermes-workspace/projects.yaml
```

Uma rota é válida somente se seu `profile` também estiver em `profiles`. Slugs e rotas duplicados são rejeitados.

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
/project use <slug>                         seleciona projeto fora de canal roteado
/project use company                        volta ao escopo organizacional
```

Em canal roteado, a rota é a autoridade: `/project use`, `/project init` e `/project create` ficam bloqueados.

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
- Contexto de projeto não deve ser promovido à memória global do agente sem decisão explícita.
- Fontes externas e informações temporais precisam ser revalidadas.
- `fail_closed_gateway: true` impede que canais sem rota recebam operações de projeto.

## Desenvolvimento

```bash
python -m unittest discover -v
python -m py_compile __init__.py scripts/project_os.py scripts/install.py
```

O GitHub Actions executa os mesmos testes.
