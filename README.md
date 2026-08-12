# Hermes Multi-Projects

Plugin independente para operar os mesmos perfis Hermes em múltiplos projetos, sem duplicar agentes nem modificar o core.

## O que resolve

- mapeia uma origem de canal para `profile + project_slug`;
- injeta contexto do projeto antes de cada chamada ao modelo;
- usa `projects/<slug>/AGENTS.md`, `PROJECT.md` e `CONTEXT.md` como fontes canônicas;
- bloqueia rotas de canal não provisionadas quando configurado em modo fechado;
- permite selecionar `company` ou um projeto fora de canais, por perfil;
- expõe uma tool para o agente consultar o contexto ativo.

> Limite explícito da V1: o Hermes atual não passa o `session_id` ao handler de comandos de plugin. Em CLI/TUI, a seleção manual é persistida por perfil, não por sessão individual. Canais roteados têm escopo determinístico por mensagem.

## Instalação

```bash
git clone https://github.com/Company-OS-IA/Hermes-Multi-Projects.git /tmp/hermes-multi-projects
python /tmp/hermes-multi-projects/scripts/install.py
```

Adicione `hermes-multi-projects` à lista `plugins.enabled` na configuração Hermes e reinicie o gateway. O instalador não toca em arquivos do core.

Use `scripts/project_os.py init` para criar um projeto e `scripts/project_os.py validate` para validar manifestos. Configure o caminho do workspace e o manifesto em `config.yaml`:

```yaml
plugins:
  entries:
    hermes-multi-projects:
      workspace_root: /srv/company-os
      manifest: /srv/company-os/projects.yaml
      fail_closed_gateway: true
```

## Manifesto

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

## Comandos

```text
/project                     # mostra o contexto atual
/project use pixel-x         # seleciona projeto fora de canal
/project use company          # volta ao escopo organizacional
/projects                    # lista projetos disponíveis ao perfil
```

No Telegram, comandos com hífen aparecem com underscore no menu quando aplicável. A seleção por rota tem precedência e não pode ser sobrescrita manualmente.

## Estrutura de projeto

```text
projects/<slug>/
├── PROJECT.md
├── CONTEXT.md
├── AGENTS.md
├── knowledge/
├── operations/
├── artifacts/
└── checkpoints/
```

## Segurança

O plugin fornece isolamento de contexto e bloqueio de rota. Ele não cria um sandbox de filesystem: ferramentas externas ainda devem respeitar as políticas Hermes e o contexto injetado. Não trate esta V1 como controle de acesso de SO.
