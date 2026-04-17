# Synapse A2A

**🌐 Language: [English](README.md) | [日本語](README.ja.md) | [中文](README.zh.md) | [한국어](README.ko.md) | Español | [Français](README.fr.md)**

> **Permite que los agentes colaboren en tareas sin cambiar su comportamiento**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-3710%20passed-brightgreen.svg)](#pruebas)
[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/s-hiraoku/synapse-a2a)

> Un framework que permite la colaboración entre agentes mediante el Protocolo Google A2A, manteniendo los agentes CLI (Claude Code, Codex, Gemini, OpenCode, GitHub Copilot CLI) **exactamente como son**

## Objetivos del Proyecto

```text
┌─────────────────────────────────────────────────────────────────┐
│  ✅ No Invasivo: No cambia el comportamiento del agente         │
│  ✅ Colaborativo: Permite que los agentes trabajen juntos       │
│  ✅ Transparente: Mantiene los flujos de trabajo existentes     │
└─────────────────────────────────────────────────────────────────┘
```

Synapse A2A **envuelve de forma transparente** la entrada/salida de cada agente sin modificar el agente en sí. Esto significa:

- **Aprovechar las fortalezas de cada agente**: Los usuarios pueden asignar libremente roles y especializaciones
- **Curva de aprendizaje cero**: Continúa usando los flujos de trabajo existentes
- **A prueba de futuro**: Resistente a las actualizaciones de los agentes

Consulta [Filosofía del Proyecto](docs/project-philosophy.md) para más detalles.

```mermaid
flowchart LR
    subgraph Terminal1["Terminal 1"]
        subgraph Agent1["synapse claude :8100"]
            Server1["Servidor A2A"]
            PTY1["PTY + Claude CLI"]
        end
    end
    subgraph Terminal2["Terminal 2"]
        subgraph Agent2["synapse codex :8120"]
            Server2["Servidor A2A"]
            PTY2["PTY + Codex CLI"]
        end
    end
    subgraph External["Externo"]
        ExtAgent["Agente Google A2A"]
    end

    Server1 <-->|"POST /tasks/send"| Server2
    Server1 <-->|"Protocolo A2A"| ExtAgent
    Server2 <-->|"Protocolo A2A"| ExtAgent
```

---

## Tabla de contenidos

- [Características](#características)
- [Requisitos Previos](#requisitos-previos)
- [Inicio Rápido](#inicio-rápido)
- [Casos de Uso](#casos-de-uso)
- [Skills](#skills)
- [Documentación](#documentación)
- [Arquitectura](#arquitectura)
- [Comandos CLI](#comandos-cli)
- [Endpoints de la API](#endpoints-de-la-api)
- [Estructura de Tareas](#estructura-de-tareas)
- [Identificación del Remitente](#identificación-del-remitente)
- [Niveles de Prioridad](#niveles-de-prioridad)
- [Agent Card](#agent-card)
- [Registro y Gestión de Puertos](#registro-y-gestión-de-puertos)
- [Seguridad de Archivos](#seguridad-de-archivos)
- [Monitor de Agentes](#monitor-de-agentes)
- [Pruebas](#pruebas)
- [Configuración (.synapse)](#configuración-synapse)
- [Desarrollo y Publicación](#desarrollo-y-publicación)

---

## Características

| Categoría | Característica |
| --------- | -------------- |
| **Compatible con A2A** | Toda la comunicación usa formato Message/Part + Task, descubrimiento de Agent Card |
| **Integración CLI** | Convierte herramientas CLI existentes en agentes A2A sin modificación |
| **synapse send** | Envía mensajes entre agentes mediante `synapse send <agente> "mensaje"` |
| **Identificación del Remitente** | Identificación automática del remitente vía `metadata.sender` + coincidencia de PID |
| **Interrupción por Prioridad** | Prioridad 5 envía SIGINT antes del mensaje (parada de emergencia) |
| **Multi-Instancia** | Ejecuta múltiples agentes del mismo tipo (asignación automática de puertos) |
| **Integración Externa** | Comunícate con otros agentes Google A2A |
| **Seguridad de Archivos** | Previene conflictos multi-agente con bloqueo de archivos y seguimiento de cambios (visible en `synapse list`) |
| **Nombrado de Agentes** | Nombres y roles personalizados para fácil identificación (`synapse send mi-claude "hola"`) |
| **Resumen de Agente** | Resumen persistente de 120 caracteres (`synapse set-summary`). Texto manual, `--auto` genera desde el contexto de Git, `--clear` elimina. Visible en Canvas, MCP `list_agents`, Agent Card `extensions.synapse`, y `synapse list --columns SUMMARY` |
| **Monitor de Agentes** | Estado en tiempo real (READY/WAITING/PROCESSING/DONE), vista previa de tarea ACTUAL, salto a terminal |
| **Historial de Tareas** | Seguimiento automático de tareas con búsqueda, exportación y estadísticas (habilitado por defecto) |
| **Tablero de Tareas Compartido** | Coordinación de tareas basada en SQLite con seguimiento de dependencias (`synapse tasks`) |
| **Puertas de Calidad** | Ganchos configurables (`on_idle`, `on_task_completed`) que controlan las transiciones de estado |
| **Aprobación de Planes** | Flujo de trabajo en modo plan con `synapse approve/reject` para revisión con intervención humana |
| **Cierre Ordenado** | `synapse kill` envía una solicitud de cierre antes de SIGTERM (tiempo de espera de 30 segundos) |
| **Modo Delegado** | `--delegate-mode` convierte a un agente en un coordinador que delega en lugar de editar archivos |
| **Generación Automática de Paneles** | `synapse team start` — el primer agente toma el control de la terminal actual, los otros en paneles nuevos |
| **Lanzar instancia única** | `synapse spawn <profile>` — Lanza un único agente en un nuevo panel o ventana de terminal |

---

## Requisitos Previos

- **SO**: macOS / Linux (Windows vía WSL2 recomendado)
- **Python**: 3.10+
- **Herramientas CLI**: Pre-instala y configura los agentes que desees usar:
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)
  - [OpenCode](https://github.com/opencode-ai/opencode)
  - [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli)

---

## Inicio Rápido

### 1. Instalar Synapse A2A

<details>
<summary><b>macOS / Linux / WSL2 (recomendado)</b></summary>

```bash
# pipx (recomendado)
pipx install synapse-a2a

# O ejecutar directamente con uvx (sin instalar)
uvx synapse-a2a claude
```

</details>

<details>
<summary><b>Windows</b></summary>

> **Se recomienda encarecidamente WSL2.** Synapse A2A usa `pty.spawn()` que requiere una terminal tipo Unix.

```bash
# Dentro de WSL2 — igual que Linux
pipx install synapse-a2a

# Scoop (experimental, WSL2 sigue siendo necesario para pty)
scoop bucket add synapse-a2a https://github.com/s-hiraoku/scoop-synapse-a2a
scoop install synapse-a2a
```

</details>

<details>
<summary><b>Desarrolladores (desde código fuente)</b></summary>

```bash
# Instalar con uv
uv sync

# O pip (editable)
pip install -e .
```

</details>

**Con soporte gRPC:**

```bash
pip install "synapse-a2a[grpc]"
```

### 2. Instalar Skills (Recomendado)

**Instalar skills es altamente recomendado para aprovechar al maximo Synapse A2A.**

Los skills ayudan a Claude a entender automáticamente las funcionalidades de Synapse A2A: mensajería @agent, Seguridad de Archivos, y más.

```bash
# Requiere GitHub CLI 2.90.0+
# https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/
gh skill install s-hiraoku/synapse-a2a synapse-a2a
gh skill install s-hiraoku/synapse-a2a synapse-manager
# Fijar una versión: gh skill install s-hiraoku/synapse-a2a synapse-a2a --pin v0.26.1
# Apuntar a un runtime de agente específico: ... --agent claude-code
```

Consulta [Skills](#skills) para más detalles. La ruta heredada
`npx skills add ...` / `skills.sh` sigue funcionando, pero ya no es
la forma recomendada de instalar. Usa `gh skill install` para fijar
versiones y rastrear procedencia.

### 3. Iniciar Agentes

```bash
# Terminal 1: Claude
synapse claude

# Terminal 2: Codex
synapse codex

# Terminal 3: Gemini
synapse gemini

# Terminal 4: OpenCode
synapse opencode

# Terminal 5: GitHub Copilot CLI
synapse copilot
```

> Nota: Si la visualización del scrollback del terminal esta distorsionada, prueba:
> ```bash
> uv run synapse gemini
> # o
> uv run python -m synapse.cli gemini
> ```

Los puertos se asignan automáticamente:

| Agente   | Rango de Puertos |
| -------- | ---------------- |
| Claude   | 8100-8109        |
| Gemini   | 8110-8119        |
| Codex    | 8120-8129        |
| OpenCode | 8130-8139        |
| Copilot  | 8140-8149        |

### 4. Comunicación Entre Agentes

Usa `synapse send` para enviar mensajes entre agentes:

```bash
synapse send codex "Por favor revisa este diseño" --from synapse-claude-8100
synapse send gemini "Sugiere mejoras para la API" --from synapse-claude-8100
```

Para múltiples instancias del mismo tipo, usa el formato tipo-puerto:

```bash
synapse send codex-8120 "Encarga esta tarea" --from synapse-claude-8100
synapse send codex-8121 "Encarga esa tarea" --from synapse-claude-8100
```

### 5. API HTTP

```bash
# Enviar mensaje
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Hello!"}]}}'

# Parada de emergencia (Prioridad 5)
curl -X POST "http://localhost:8100/tasks/send-priority?priority=5" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Stop!"}]}}'
```

---

## Casos de Uso

### 1. Consulta Rápida de Especificaciones (Simple)
Mientras programas con **Claude**, consulta rápidamente a **Gemini** (mejor en búsquedas web) para obtener las últimas especificaciones de librerías o información de errores sin cambiar de contexto.

```bash
# En la terminal de Claude:
synapse send gemini "Resume las nuevas funcionalidades de f-string en Python 3.12" --from synapse-claude-8100
```

### 2. Revisión Cruzada de Diseños (Intermedio)
Obtener retroalimentación sobre tu diseño desde agentes con diferentes perspectivas.

```bash
# Después de que Claude redacte un diseño:
synapse send gemini "Revisa críticamente este diseño desde perspectivas de escalabilidad y mantenibilidad" --from synapse-claude-8100
```

### 3. Programación en Parejas TDD (Intermedio)
Separar "escritor de pruebas" e "implementador" para código robusto.

```bash
# Terminal 1 (Codex):
Crea pruebas unitarias para auth.py - caso normal y caso de expiración de token.

# Terminal 2 (Claude):
synapse send codex-8120 "Implementa auth.py para que pase las pruebas que creaste" --from synapse-claude-8100
```

### 4. Auditoría de Seguridad (Especializado)
Haz que un agente con rol de experto en seguridad audite tu código antes de hacer commit.

```bash
# Asigna un rol a Gemini:
Eres un ingeniero de seguridad. Revisa solo vulnerabilidades (SQLi, XSS, etc.)

# Después de escribir código:
synapse send gemini "Audita los cambios actuales (git diff)" --from synapse-claude-8100
```

### 5. Corrección Automática desde Logs de Error (Avanzado)
Pasa logs de error a un agente para sugerencias de corrección automática.

```bash
# Las pruebas fallaron...
pytest > error.log

# Pedir al agente que corrija
synapse send claude "Lee error.log y corrige el problema en synapse/server.py" --from synapse-gemini-8110
```

### 6. Migración de Lenguaje/Framework (Avanzado)
Distribuir trabajo de refactorización grande entre agentes.

```bash
# Terminal 1 (Claude):
Lee legacy_api.js y crea definiciones de tipos TypeScript

# Terminal 2 (Codex):
synapse send claude "Usa las definiciones de tipos que creaste para reescribir legacy_api.js a src/new_api.ts" --from synapse-codex-8121
```

### Comparacion con SSH Remoto

| Operacion | SSH | Synapse |
|-----------|-----|---------|
| Operacion CLI manual | ◎ | ◎ |
| Envío programatico de tareas | △ requiere expect etc. | ◎ API HTTP |
| Múltiples clientes simultáneos | △ múltiples sesiones | ◎ endpoint único |
| Notificaciones de progreso en tiempo real | ✗ | ◎ SSE/Webhook |
| Coordinación automática entre agentes | ✗ | ◎ synapse send |

> **Nota**: SSH es frecuentemente suficiente para uso individual de CLI. Synapse destaca cuando necesitas automatización, coordinación y colaboración multi-agente.

---

## Skills

**Instalar skills es altamente recomendado** al usar Synapse A2A con Claude Code.

### Por que Instalar Skills?

Con los skills instalados, Claude entiende y ejecuta automáticamente:

- **synapse send**: Comunicación entre agentes vía `synapse send codex "Corrige esto" --from synapse-claude-8100`
- **Control de prioridad**: Envío de mensajes con Prioridad 1-5 (5 = parada de emergencia)
- **Seguridad de Archivos**: Previene conflictos multi-agente con bloqueo de archivos y seguimiento de cambios
- **Gestión de historial**: Búsqueda, exportación y estadísticas del historial de tareas

### Instalación

Instala con GitHub CLI (**requiere `gh` 2.90.0+**):

```bash
# Instalar skills principales desde este repositorio
gh skill install s-hiraoku/synapse-a2a synapse-a2a
gh skill install s-hiraoku/synapse-a2a synapse-manager

# Fijar a una etiqueta de lanzamiento para que las actualizaciones sean explícitas
gh skill install s-hiraoku/synapse-a2a synapse-a2a --pin v0.26.1

# Instalar para un runtime de agente específico
gh skill install s-hiraoku/synapse-a2a synapse-a2a --agent claude-code
gh skill install s-hiraoku/synapse-a2a synapse-a2a --agent copilot

# Previsualizar un skill antes de instalarlo
gh skill preview s-hiraoku/synapse-a2a synapse-a2a

# Comprobar cambios upstream en los skills instalados
gh skill update
```

El frontmatter de `SKILL.md` de cada skill instalado registra el repositorio
de origen, el ref y el tree SHA, por lo que `gh skill update` puede detectar
drift y `--pin` te da una versión determinista.

**Ruta heredada** — `npx skills add s-hiraoku/synapse-a2a`
(skills.sh) sigue funcionando para instalaciones antiguas de `gh`, pero
`gh skill` es la herramienta recomendada de ahora en adelante. Consulta
[`docs/skills-management.md`](docs/skills-management.md) para la matriz
de migración.

### Skills Incluidos

| Skill | Descripción |
|-------|-------------|
| **synapse-a2a** | Guía completa para comunicación entre agentes: `synapse send`, prioridad, protocolo A2A, historial, Seguridad de Archivos, configuración |

### Gestión de Skills

Synapse incluye un administrador de skills integrado con un almacén central (`~/.synapse/skills/`) para organizar y desplegar skills entre agentes.

#### Ámbitos de Skills

| Ámbito | Ubicación | Descripción |
|-------|----------|-------------|
| **Synapse** | `~/.synapse/skills/` | Almacén central (desplegar a agentes desde aquí) |
| **Usuario** | `~/.claude/skills/`, `~/.agents/skills/`, etc. | Skills para todo el usuario |
| **Proyecto** | `./.claude/skills/`, `./.agents/skills/`, etc. | Skills locales del proyecto |
| **Plugin** | `./plugins/*/skills/` | Skills de plugins de solo lectura |

#### Comandos

```bash
# TUI interactivo
synapse skills

# Listar y explorar
synapse skills list                          # Todos los ámbitos
synapse skills list --scope synapse          # Solo almacén central
synapse skills show <nombre>                 # Detalles del skill

# Administrar
synapse skills delete <nombre> [--force]
synapse skills move <nombre> --to <ámbito>

# Operaciones del almacén central
synapse skills import <nombre>                 # Importar desde directorios de agentes al almacén central
synapse skills deploy <nombre> --agent claude,codex --scope user
synapse skills add <repo>                    # Instalar desde repo (envoltura de npx skills)
synapse skills create                        # Crear nueva plantilla de skill

# Conjuntos de skills (grupos nombrados)
synapse skills set list
synapse skills set show <nombre>
```

### Estructura de Directorios

```text
plugins/
└── synapse-a2a/
    ├── .claude-plugin/plugin.json
    ├── README.md
    └── skills/
        └── synapse-a2a/SKILL.md
```

Consulta [plugins/synapse-a2a/README.md](plugins/synapse-a2a/README.md) para más detalles.

> **Nota**: Codex y Gemini no soportan plugins, pero puedes colocar skills expandidos en el directorio `.agents/skills/` para habilitar estas funcionalidades.

---

## Documentación

- [guides/README.md](guides/README.md) - Resumen de la documentacion
- [guides/multi-agent-setup.md](guides/multi-agent-setup.md) - Guía de configuración
- [guides/usage.md](guides/usage.md) - Comandos y patrones de uso
- [guides/settings.md](guides/settings.md) - Detalles de configuración `.synapse`
- [guides/troubleshooting.md](guides/troubleshooting.md) - Problemas comunes y soluciones

---

## Arquitectura

### Estructura Servidor/Cliente A2A

En Synapse, **cada agente opera como un servidor A2A**. No hay servidor central; es una arquitectura P2P.

```
┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│  synapse claude (puerto 8100)       │    │  synapse codex (puerto 8120)        │
│  ┌───────────────────────────────┐  │    │  ┌───────────────────────────────┐  │
│  │  Servidor FastAPI (Serv. A2A) │  │    │  │  Servidor FastAPI (Serv. A2A) │  │
│  │  /.well-known/agent.json      │  │    │  │  /.well-known/agent.json      │  │
│  │  /tasks/send                  │◄─┼────┼──│  A2AClient                    │  │
│  │  /tasks/{id}                  │  │    │  └───────────────────────────────┘  │
│  └───────────────────────────────┘  │    │  ┌───────────────────────────────┐  │
│  ┌───────────────────────────────┐  │    │  │  PTY + Codex CLI              │  │
│  │  PTY + Claude CLI             │  │    │  └───────────────────────────────┘  │
│  └───────────────────────────────┘  │    └─────────────────────────────────────┘
└─────────────────────────────────────┘
```

Cada agente es:

- **Servidor A2A**: Acepta solicitudes de otros agentes
- **Cliente A2A**: Envía solicitudes a otros agentes

### Componentes Principales

| Componente | Archivo | Rol |
| ---------- | ------- | --- |
| Servidor FastAPI | `synapse/server.py` | Proporciona endpoints A2A |
| Router A2A | `synapse/a2a_compat.py` | Implementacion del protocolo A2A |
| Cliente A2A | `synapse/a2a_client.py` | Comunicación con otros agentes |
| TerminalController | `synapse/controller.py` | Gestión de PTY, detección READY/PROCESSING |
| Shell | `synapse/shell.py` | Shell interactivo con enrutamiento de patrones @Agent |
| AgentRegistry | `synapse/registry.py` | Registro y búsqueda de agentes |
| SkillManager | `synapse/skills.py` | Descubrimiento, despliegue e importación de skills, conjuntos de skills |
| SkillManagerCmd | `synapse/commands/skill_manager.py` | TUI y CLI de administración de skills |

### Secuencia de Inicio

```mermaid
sequenceDiagram
    participant Synapse as Servidor Synapse
    participant Registry as AgentRegistry
    participant PTY as TerminalController
    participant CLI as Agente CLI

    Synapse->>Registry: 1. Registrar agente (agent_id, pid, puerto)
    Synapse->>PTY: 2. Iniciar PTY
    PTY->>CLI: 3. Iniciar agente CLI
    Synapse->>PTY: 4. Enviar instrucciones iniciales (remitente: synapse-system)
    PTY->>CLI: 5. La IA recibe instrucciones iniciales
```

### Flujo de Comunicación

```mermaid
sequenceDiagram
    participant User as Usuario
    participant Claude as Claude (8100)
    participant Client as A2AClient
    participant Codex as Codex (8120)

    User->>Claude: @codex Revisa este diseño
    Claude->>Client: send_to_local()
    Client->>Codex: POST /tasks/send-priority
    Codex->>Codex: Crear Task → Escribir en PTY
    Codex-->>Client: {"task": {"id": "...", "status": "working"}}
    Client-->>Claude: [→ codex] Envío completado
```

---

## Comandos CLI

### Operaciones Basicas

```bash
# Iniciar agente (primer plano)
synapse claude
synapse codex
synapse gemini
synapse opencode
synapse copilot

# Iniciar con nombre y rol personalizado
synapse claude --name mi-claude --role "revisor de código"

# Saltar configuración interactiva de nombre/rol
synapse claude --no-setup

# Especificar puerto
synapse claude --port 8105

# Pasar argumentos a la herramienta CLI
synapse claude -- --resume
```

### Nombrado de Agentes

Asigna nombres y roles personalizados a los agentes para una identificación y gestión más fácil:

```bash
# Configuración interactiva (por defecto al iniciar agente)
synapse claude
# → Solicita nombre y rol

# Saltar configuración interactiva
synapse claude --no-setup

# Establecer nombre y rol vía opciones CLI
synapse claude --name mi-claude --role "revisor de código"

# Después de que el agente esta corriendo, cambiar nombre/rol
synapse rename synapse-claude-8100 --name mi-claude --role "escritor de pruebas"
synapse rename mi-claude --role "documentacion"  # Cambiar solo el rol
synapse rename mi-claude --clear                 # Limpiar nombre y rol
```

Una vez nombrado, usa el nombre personalizado para todas las operaciones:

```bash
synapse send mi-claude "Revisa este código" --from synapse-codex-8121
synapse jump mi-claude
synapse kill mi-claude
```

**Nombre vs ID:**
- **Visualización/Prompts**: Muestra el nombre si esta establecido, de lo contrario el ID (ej., `Kill mi-claude (PID: 1234)?`)
- **Procesamiento interno**: Siempre usa el Runtime ID (`synapse-claude-8100`)
- **Resolucion de destino**: El nombre tiene la mayor prioridad al hacer coincidencia de destinos

### Lista de Comandos

| Comando | Descripción |
| ------- | ----------- |
| `synapse <profile>` | Iniciar en primer plano |
| `synapse start <profile>` | Iniciar en segundo plano |
| `synapse stop <profile\|id>` | Detener agente (puede especificar ID) |
| `synapse kill <destino>` | Cierre ordenado (envía solicitud de cierre, luego SIGTERM tras 30s) |
| `synapse kill <destino> -f` | Cierre forzado (SIGKILL inmediato) |
| `synapse jump <destino>` | Saltar a la terminal del agente |
| `synapse rename <destino>` | Asignar nombre/rol al agente |
| `synapse set-summary <destino> [texto]` | Establecer resumen persistente del agente (120 car.). `--auto` genera desde el contexto de Git, `--clear` elimina |
| `synapse --version` | Mostrar version |
| `synapse list` | Listar agentes en ejecución (Rich TUI con auto-actualizacion y salto a terminal) |
| `synapse logs <profile>` | Mostrar logs |
| `synapse send <destino> <mensaje>` | Enviar mensaje |
| `synapse reply <mensaje>` | Responder al último mensaje A2A recibido |
| `synapse trace <task_id>` | Mostrar historial de tareas + referencia cruzada de seguridad de archivos |
| `synapse instructions show` | Mostrar contenido de instrucciones |
| `synapse instructions files` | Listar archivos de instrucciones |
| `synapse instructions send` | Reenviar instrucciones iniciales |
| `synapse history list` | Mostrar historial de tareas |
| `synapse history show <task_id>` | Mostrar detalles de tarea |
| `synapse history search` | Búsqueda por palabras clave |
| `synapse history cleanup` | Eliminar datos antiguos |
| `synapse history stats` | Mostrar estadísticas |
| `synapse history export` | Exportar a JSON/CSV |
| `synapse file-safety status` | Mostrar estadísticas de seguridad de archivos |
| `synapse file-safety locks` | Listar bloqueos activos |
| `synapse file-safety lock` | Bloquear un archivo |
| `synapse file-safety unlock` | Liberar bloqueo |
| `synapse file-safety history` | Historial de cambios de archivos |
| `synapse file-safety recent` | Cambios recientes |
| `synapse file-safety record` | Registrar cambio manualmente |
| `synapse file-safety cleanup` | Eliminar datos antiguos |
| `synapse file-safety debug` | Mostrar información de depuración |
| `synapse skills` | Administrador de skills (TUI interactivo) |
| `synapse skills list` | Listar skills descubiertos |
| `synapse skills show <nombre>` | Mostrar detalles del skill |
| `synapse skills delete <nombre>` | Eliminar un skill |
| `synapse skills move <nombre>` | Mover skill a otro ámbito |
| `synapse skills deploy <nombre>` | Desplegar skill desde almacén central a directorios de agentes |
| `synapse skills import <nombre>` | Importar skill al almacén central (~/.synapse/skills/) |
| `synapse skills add <repo>` | Instalar skill desde repositorio (vía npx skills) |
| `synapse skills create` | Crear un nuevo skill |
| `synapse skills set list` | Listar conjuntos de skills |
| `synapse skills set show <nombre>` | Mostrar detalles del conjunto de skills |
| `synapse config` | Gestión de configuración (TUI interactivo) |
| `synapse config show` | Mostrar configuración actual |
| `synapse tasks list` | Listar tablero de tareas compartido |
| `synapse tasks create` | Crear una tarea |
| `synapse tasks assign` | Asignar tarea a un agente |
| `synapse tasks complete` | Marcar tarea como completada |
| `synapse approve <task_id>` | Aprobar un plan |
| `synapse reject <task_id>` | Rechazar un plan con motivo |
| `synapse team start` | Lanzar agentes (1º=traspaso, resto=nuevos paneles). `--all-new` para todos nuevos |
| `synapse spawn <profile>` | Lanzar un único agente en un nuevo panel |

### Modo Resume

Al reanudar una sesion existente, usa estas banderas para **omitir el envio de instrucciones iniciales** (explicacion del protocolo A2A), manteniendo tu contexto limpio:

```bash
# Reanudar sesion de Claude Code
synapse claude -- --resume

# Reanudar Gemini con historial
synapse gemini -- --resume=5

# Codex usa 'resume' como subcomando (no bandera --resume)
synapse codex -- resume --last
```

Banderas por defecto (personalizables en `settings.json`):
- **Claude**: `--resume`, `--continue`, `-r`, `-c`
- **Gemini**: `--resume`, `-r`
- **Codex**: `resume`
- **OpenCode**: `--continue`, `-c`
- **Copilot**: `--continue`, `--resume`

### Gestión de Instrucciones

Reenvia manualmente las instrucciones iniciales cuando no fueron enviadas (ej., después del modo `--resume`):

```bash
# Mostrar contenido de instrucciones
synapse instructions show claude

# Listar archivos de instrucciones
synapse instructions files claude

# Enviar instrucciones iniciales al agente en ejecución
synapse instructions send claude

# Vista previa antes de enviar
synapse instructions send claude --preview

# Enviar a un Runtime ID especifico
synapse instructions send synapse-claude-8100
```

Util cuando:
- Necesitas información del protocolo A2A después de iniciar con `--resume`
- El agente perdio/olvido instrucciones y necesita recuperacion
- Depuración del contenido de instrucciones

### Gestión de Agentes Externos

```bash
# Registrar agente externo
synapse external add http://other-agent:9000 --alias otro

# Listar
synapse external list

# Enviar mensaje
synapse external send otro "Procesa esta tarea"
```

### Gestión del Historial de Tareas

Busca, navega y analiza resultados de ejecución de agentes pasados.

**Nota:** El historial esta habilitado por defecto desde v0.3.13. Para deshabilitarlo:

```bash
# Deshabilitar vía variable de entorno
export SYNAPSE_HISTORY_ENABLED=false
synapse claude
```

#### Operaciones Basicas

```bash
# Mostrar las últimas 50 entradas
synapse history list

# Filtrar por agente
synapse history list --agent claude

# Limite personalizado
synapse history list --limit 100

# Mostrar detalles de tarea
synapse history show task-id-uuid
```

#### Búsqueda por Palabras Clave

Busca en los campos de entrada/salida por palabra clave:

```bash
# Palabra clave unica
synapse history search "Python"

# Múltiples palabras clave (logica OR)
synapse history search "Python" "Docker"

# Logica AND (todas las palabras clave deben coincidir)
synapse history search "Python" "function" --logic AND

# Con filtro de agente
synapse history search "Python" --agent claude

# Limitar resultados
synapse history search "error" --limit 20
```

#### Estadísticas

```bash
# Estadísticas generales (total, tasa de exito, desglose por agente)
synapse history stats

# Estadísticas de un agente especifico
synapse history stats --agent claude
```

#### Exportación de Datos

```bash
# Exportar JSON (stdout)
synapse history export --format json

# Exportar CSV
synapse history export --format csv

# Guardar en archivo
synapse history export --format json --output history.json
synapse history export --format csv --agent claude > claude_history.csv
```

#### Politica de Retencion

```bash
# Eliminar datos con más de 30 dias
synapse history cleanup --days 30

# Mantener base de datos por debajo de 100MB
synapse history cleanup --max-size 100

# Forzar (sin confirmación)
synapse history cleanup --days 30 --force

# Ejecución en seco
synapse history cleanup --days 30 --dry-run
```

**Almacenamiento:**

- Base de datos SQLite: `~/.synapse/history/history.db`
- Almacena: ID de tarea, nombre del agente, entrada, salida, estado, metadatos
- Indexado automático: agent_name, timestamp, task_id

**Configuración:**

- **Habilitado por defecto** (v0.3.13+)
- **Deshabilitar**: `SYNAPSE_HISTORY_ENABLED=false`

### Comando synapse send (Recomendado)

Usa `synapse send` para comunicación entre agentes. Funciona en entornos sandbox.

```bash
synapse send <destino> "<mensaje>" [--from <remitente>] [--priority <1-5>] [--wait | --notify | --silent]
```

**Formatos de Destino:**

| Formato | Ejemplo | Descripción |
|---------|---------|-------------|
| Nombre personalizado | `my-claude` | Mayor prioridad, coincidir nombre en registro |
| Runtime ID completo | `synapse-claude-8100` | Coincidir Runtime ID exacto |
| Tipo-puerto | `claude-8100` | Coincidir tipo y puerto abreviado |
| Tipo de agente | `claude` | Solo funciona cuando existe una única instancia |

Cuando hay múltiples agentes del mismo tipo en ejecución, solo el tipo (ej., `claude`) dará error. Usa `claude-8100` o `synapse-claude-8100`.

**Opciones:**

| Opción | Corto | Descripción |
|--------|-------|-------------|
| `--from` | `-f` | Runtime ID del remitente (opcional; auto-detectado) |
| `--priority` | `-p` | Prioridad 1-4: normal, 5: parada de emergencia (envía SIGINT) |
| `--wait` | - | Bloqueo síncrono - esperar a que el receptor responda con `synapse reply` |
| `--notify` | - | Notificación asíncrona - recibir notificación cuando la tarea termine (predeterminado) |
| `--silent` | - | Enviar y olvidar - no se requiere respuesta ni notificación |
| `--force` | - | Omitir la comprobación de desajuste del directorio de trabajo |

**Elegir modo de respuesta:**

| Tipo de mensaje | Bandera | Ejemplo |
|-----------------|---------|---------|
| Pregunta | `--wait` | "¿Cuál es el estado?" |
| Solicitud de análisis | `--wait` | "Por favor, revisa este código" |
| Tarea con resultado esperado | `--notify` | "Ejecuta las pruebas e informa los resultados" |
| Tarea delegada (enviar y olvidar) | `--silent` | "Corrige este error y haz commit" |
| Notificación | `--silent` | "FYI: Compilación completada" |

El valor predeterminado es `--notify` (notificación asíncrona al finalizar).

**Ejemplos:**

```bash
# Tarea con resultado esperado (notificación asíncrona - predeterminado)
synapse send gemini "Analiza esto e informa los hallazgos" --notify

# Tarea que requiere respuesta inmediata (bloqueo)
synapse send gemini "¿Cuál es el mejor enfoque?" --wait

# Tarea delegada, enviar y olvidar
synapse send codex "Corrige este error y haz commit" --silent

# Enviar mensaje (instancia única; --from auto-detectado)
synapse send claude "Hola" --priority 1

# Soporte para mensajes largos (cambio automático a archivo temporal)
synapse send claude --message-file /path/to/mensaje.txt --silent
echo "contenido muy largo..." | synapse send claude --stdin --silent

# Archivos adjuntos
synapse send claude "Revisa esto" --attach src/main.py --wait

# Enviar a instancia específica (múltiples del mismo tipo)
synapse send claude-8100 "Hola"

# Parada de emergencia
synapse send claude "Detente!" --priority 5

# Omitir comprobación de directorio de trabajo
synapse send claude "Revisa esto" --force

# --from explícito (solo necesario en entornos como Codex)
synapse send claude "Hola" --from $SYNAPSE_AGENT_ID
```

**Comportamiento predeterminado:** Por defecto se utiliza `--notify` (notificación asíncrona al completar).

**Importante:** Siempre usa `--from` con tu Runtime ID (formato: `synapse-<tipo>-<puerto>`).

### Comando synapse reply

Responder al último mensaje recibido:

```bash
synapse reply "<mensaje>"
```

La bandera `--from` solo es necesaria en entornos sandbox (como Codex). Sin `--from`, Synapse detecta automaticamente el remitente.

### Herramienta A2A de Bajo Nivel

Para operaciones avanzadas:

```bash
# Listar agentes
python -m synapse.tools.a2a list

# Enviar mensaje
python -m synapse.tools.a2a send --target claude --priority 1 "Hello"

# Responder al último mensaje recibido (usa seguimiento de respuestas)
python -m synapse.tools.a2a reply "Here is my response"
```

---

## Endpoints de la API

### Compatible con A2A

| Endpoint | Método | Descripción |
| -------- | ------ | ----------- |
| `/.well-known/agent.json` | GET | Agent Card |
| `/tasks/send` | POST | Enviar mensaje |
| `/tasks/send-priority` | POST | Enviar con prioridad |
| `/tasks/create` | POST | Crear tarea (sin envío PTY, para `--wait`) |
| `/tasks/{id}` | GET | Obtener estado de tarea |
| `/tasks` | GET | Listar tareas |
| `/tasks/{id}/cancel` | POST | Cancelar tarea |
| `/status` | GET | Estado READY/PROCESSING |

### Equipos de Agentes

| Endpoint | Método | Descripción |
| -------- | ------ | ----------- |
| `/tasks/board` | GET | Listar tablero de tareas compartido |
| `/tasks/board` | POST | Crear tarea en el tablero |
| `/tasks/board/{id}/claim` | POST | Reclamar tarea atómicamente |
| `/tasks/board/{id}/complete` | POST | Completar tarea |
| `/tasks/{id}/approve` | POST | Aprobar un plan |
| `/tasks/{id}/reject` | POST | Rechazar un plan con motivo |
| `/team/start` | POST | Iniciar múltiples agentes en paneles de terminal (iniciado por A2A) |
| `/spawn` | POST | Iniciar un único agente en un panel de terminal (iniciado por A2A) |

### Extensiones de Synapse

| Endpoint | Método | Descripción |
| -------- | ------ | ----------- |
| `/reply-stack/get` | GET | Obtener info del remitente sin eliminar (para vista previa antes de enviar) |
| `/reply-stack/pop` | GET | Extraer info del remitente del mapa de respuestas (para `synapse reply`) |
| `/tasks/{id}/subscribe` | GET | Suscribirse a actualizaciones de tareas vía SSE |

### Webhooks

| Endpoint | Método | Descripción |
| -------- | ------ | ----------- |
| `/webhooks` | POST | Registrar un webhook para notificaciones de tareas |
| `/webhooks` | GET | Listar webhooks registrados |
| `/webhooks` | DELETE | Eliminar un webhook |
| `/webhooks/deliveries` | GET | Intentos recientes de entrega de webhooks |

### Agentes Externos

| Endpoint | Método | Descripción |
| -------- | ------ | ----------- |
| `/external/discover` | POST | Registrar agente externo |
| `/external/agents` | GET | Listar |
| `/external/agents/{alias}` | DELETE | Eliminar |
| `/external/agents/{alias}/send` | POST | Enviar |

---

## Estructura de Tareas

En el protocolo A2A, toda la comunicación se gestiona como **Tareas** (Tasks).

### Ciclo de Vida de una Tarea

```mermaid
stateDiagram-v2
    [*] --> submitted: POST /tasks/send
    submitted --> working: Comienza el procesamiento
    working --> completed: Exito
    working --> failed: Error
    working --> input_required: Esperando entrada
    input_required --> working: Entrada recibida
    completed --> [*]
    failed --> [*]
```

### Objeto Task

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "context_id": "conversation-123",
  "status": "working",
  "message": {
    "role": "user",
    "parts": [{ "type": "text", "text": "Review this design" }]
  },
  "artifacts": [],
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100"
    }
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

### Descripción de Campos

| Campo | Tipo | Descripción |
| ----- | ---- | ----------- |
| `id` | string | Identificador único de tarea (UUID) |
| `context_id` | string? | ID de contexto de conversacion (para multi-turno) |
| `status` | string | `submitted` / `working` / `completed` / `failed` / `input_required` |
| `message` | Message | Mensaje enviado |
| `artifacts` | Artifact[] | Artefactos de salida de la tarea |
| `metadata` | object | Información del remitente (`metadata.sender`) |
| `created_at` | string | Marca de tiempo de creacion (ISO 8601) |
| `updated_at` | string | Marca de tiempo de actualizacion (ISO 8601) |

### Estructura del Mensaje

```json
{
  "role": "user",
  "parts": [
    { "type": "text", "text": "Message content" },
    {
      "type": "file",
      "file": {
        "name": "doc.pdf",
        "mimeType": "application/pdf",
        "bytes": "..."
      }
    }
  ]
}
```

| Tipo de Part | Descripción |
| ------------ | ----------- |
| `text` | Mensaje de texto |
| `file` | Archivo adjunto |
| `data` | Datos estructurados |

---

## Identificación del Remitente

El remitente de los mensajes A2A puede identificarse mediante `metadata.sender`.

### Formato de Salida PTY

Los mensajes se envían al PTY del agente con un prefijo que incluye identificación opcional del remitente y expectativas de respuesta:

```
A2A: [From: NOMBRE (ID_REMITENTE)] [REPLY EXPECTED] <contenido del mensaje>
```

- **From**: Identifica el nombre visible del remitente y su Runtime ID único.
- **REPLY EXPECTED**: Indica que el remitente está esperando una respuesta (bloqueante).

Si la información del remitente no está disponible, se recurre a:
- `A2A: [From: ID_REMITENTE] <contenido del mensaje>`
- `A2A: <contenido del mensaje>` (formato de compatibilidad hacia atrás)

### Manejo de Respuestas

Synapse gestiona automáticamente el enrutamiento de respuestas. Los agentes simplemente usan `synapse reply`:

```bash
synapse reply "Aquí esta mi respuesta"
```

El framework rastrea internamente la información del remitente y enruta las respuestas automáticamente.

### Verificación de la API de Tareas (Desarrollo)

```bash
curl -s http://localhost:8120/tasks/<id> | jq '.metadata.sender'
```

Respuesta:

```json
{
  "sender_id": "synapse-claude-8100",
  "sender_type": "claude",
  "sender_endpoint": "http://localhost:8100"
}
```

### Cómo Funciona

1. **Al enviar**: Consulta el Registry, identifica el propio agent_id mediante coincidencia de PID
2. **Al crear Task**: Adjunta información del remitente a `metadata.sender`
3. **Al recibir**: Verifica mediante prefijo PTY o la API de Tareas

---

## Niveles de Prioridad

| Prioridad | Comportamiento | Caso de Uso |
| --------- | -------------- | ----------- |
| 1-4 | Escritura normal en stdin | Mensajes regulares |
| 5 | SIGINT y luego escritura | Parada de emergencia |

```bash
# Parada de emergencia
synapse send claude "Detente!" --priority 5
```

---

## Agent Card

Cada agente publica un Agent Card en `/.well-known/agent.json`.

```bash
curl http://localhost:8100/.well-known/agent.json
```

```json
{
  "name": "Synapse Claude",
  "description": "PTY-wrapped claude CLI agent with A2A communication",
  "url": "http://localhost:8100",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "multiTurn": true
  },
  "skills": [
    {
      "id": "chat",
      "name": "Chat",
      "description": "Send messages to the CLI agent"
    },
    {
      "id": "interrupt",
      "name": "Interrupt",
      "description": "Interrupt current processing"
    }
  ],
  "extensions": {
    "synapse": {
      "agent_id": "synapse-claude-8100",
      "pty_wrapped": true,
      "priority_interrupt": true,
      "at_agent_syntax": true
    }
  }
}
```

### Filosofía de Diseño

El Agent Card es una "tarjeta de presentación" que contiene solo información orientada al exterior:

- capabilities, skills, endpoint, etc.
- Las instrucciones internas no se incluyen (se envian vía A2A Task al inicio)

---

## Registro y Gestión de Puertos

### Archivos del Registro

```
~/.a2a/registry/
├── synapse-claude-8100.json
├── synapse-claude-8101.json
└── synapse-gemini-8110.json
```

### Limpieza Automática

Las entradas obsoletas se eliminan automáticamente durante:

- Ejecución de `synapse list`
- Envío de mensajes (cuando el destino esta inactivo)

### Rangos de Puertos

```python
PORT_RANGES = {
    "claude": (8100, 8109),
    "gemini": (8110, 8119),
    "codex": (8120, 8129),
    "opencode": (8130, 8139),
    "copilot": (8140, 8149),
    "dummy": (8190, 8199),
}
```

### Uso Típico de Memoria (Agentes Residentes)

En macOS, los agentes residentes inactivos son ligeros. A fecha de 25 de enero de 2026,
el RSS es de aproximadamente ~12 MB por proceso de agente en una configuración de desarrollo típica.

El uso real varía según el perfil, plugins, configuración de historial y carga de trabajo.
Ten en cuenta que `ps` reporta RSS en KB (por lo que ~12 MB corresponde a ~12,000 KB).
Para medir en tu máquina:

```bash
ps -o pid,comm,rss,vsz,etime,command -A | rg "synapse"
```

Si no tienes ripgrep:

```bash
ps -o pid,comm,rss,vsz,etime,command -A | grep "synapse"
```

---

## Seguridad de Archivos

Previene conflictos cuando múltiples agentes editan los mismos archivos simultáneamente.

```mermaid
sequenceDiagram
    participant Claude
    participant FS as Seguridad de Archivos
    participant Gemini

    Claude->>FS: acquire_lock("auth.py")
    FS-->>Claude: ADQUIRIDO

    Gemini->>FS: validate_write("auth.py")
    FS-->>Gemini: DENEGADO (bloqueado por claude)

    Claude->>FS: release_lock("auth.py")
    Gemini->>FS: acquire_lock("auth.py")
    FS-->>Gemini: ADQUIRIDO
```

### Características

| Característica | Descripción |
|----------------|-------------|
| **Bloqueo de Archivos** | Control exclusivo previene edicion simultanea |
| **Seguimiento de Cambios** | Registra quien cambio que y cuando |
| **Inyeccion de Contexto** | Proporciona historial de cambios recientes en lectura |
| **Validacion Pre-escritura** | Verifica estado del bloqueo antes de escribir |
| **Integración con List** | Bloqueos activos visibles en la columna EDITING_FILE de `synapse list` |

### Habilitar

```bash
# Habilitar vía variable de entorno
export SYNAPSE_FILE_SAFETY_ENABLED=true
synapse claude
```

### Comandos Basicos

```bash
# Mostrar estadísticas
synapse file-safety status

# Listar bloqueos activos
synapse file-safety locks

# Adquirir bloqueo
synapse file-safety lock /path/to/file.py claude --intent "Refactorización"

# Esperar a que se libere el bloqueo
synapse file-safety lock /path/to/file.py claude --wait --wait-timeout 60 --wait-interval 2

# Liberar bloqueo
synapse file-safety unlock /path/to/file.py claude

# Historial de cambios de archivo
synapse file-safety history /path/to/file.py

# Cambios recientes
synapse file-safety recent

# Eliminar datos antiguos
synapse file-safety cleanup --days 30
```

### API Python

```python
from synapse.file_safety import FileSafetyManager, ChangeType, LockStatus

manager = FileSafetyManager.from_env()

# Adquirir bloqueo
result = manager.acquire_lock("/path/to/file.py", "claude", intent="Refactorización")
if result["status"] == LockStatus.ACQUIRED:
    # Editar archivo...

    # Registrar cambio
    manager.record_modification(
        file_path="/path/to/file.py",
        agent_name="claude",
        task_id="task-123",
        change_type=ChangeType.MODIFY,
        intent="Corregir error de autenticacion"
    )

    # Liberar bloqueo
    manager.release_lock("/path/to/file.py", "claude")

# Validacion pre-escritura
validation = manager.validate_write("/path/to/file.py", "gemini")
if not validation["allowed"]:
    print(f"Escritura bloqueada: {validation['reason']}")
```

**Almacenamiento**: Por defecto es `.synapse/file_safety.db` (SQLite, relativo al directorio de trabajo). Cambiar vía `SYNAPSE_FILE_SAFETY_DB_PATH` (ej., `~/.synapse/file_safety.db` para global).

Consulta [docs/file-safety.md](docs/file-safety.md) para más detalles.

---

## Monitor de Agentes

Monitoreo en tiempo real del estado de los agentes con capacidad de salto a terminal.

### Modo Rich TUI

```bash
# Iniciar Rich TUI con auto-actualizacion (por defecto)
synapse list
```

La visualización se actualiza automáticamente cuando cambia el estado de los agentes (vía file watcher) con un intervalo de sondeo de respaldo de 10 segundos.

### Columnas de Visualización

| Columna | Descripción |
|---------|-------------|
| ID | ID de ejecución (ej., `synapse-claude-8100`) |
| NAME | Nombre personalizado (si esta asignado) |
| TYPE | Tipo de agente (claude, gemini, codex, etc.) |
| ROLE | Descripción del rol del agente (si esta asignado) |
| STATUS | Estado actual (READY, WAITING, PROCESSING, DONE) |
| CURRENT | Vista previa de la tarea actual |
| TRANSPORT | Indicador de transporte de comunicación |
| WORKING_DIR | Directorio de trabajo actual |
| SUMMARY | Resumen persistente del agente (opt-in, no incluido en columnas por defecto) |
| EDITING_FILE | Archivo siendo editado (solo con Seguridad de Archivos habilitada) |

**Personalizar columnas** en `settings.json`:

```json
{
  "list": {
    "columns": ["ID", "NAME", "STATUS", "CURRENT", "TRANSPORT", "WORKING_DIR"]
  }
}
```

### Estados

| Estado | Color | Significado |
|--------|-------|-------------|
| **READY** | Verde | El agente esta inactivo, esperando entrada |
| **WAITING** | Cian | El agente muestra UI de selección, esperando decision del usuario |
| **PROCESSING** | Amarillo | El agente esta trabajando activamente |
| **DONE** | Azul | Tarea completada (transiciona automáticamente a READY después de 10s) |

### Controles Interactivos

| Tecla | Accion |
|-------|--------|
| 1-9 | Seleccionar fila de agente (directo) |
| ↑/↓ | Navegar filas de agentes |
| **Enter** o **j** | Saltar a la terminal del agente seleccionado |
| **k** | Matar agente seleccionado (con confirmación) |
| **/** | Filtrar por TYPE, NAME o WORKING_DIR |
| ESC | Limpiar filtro/selección |
| q | Salir |

**Terminales Soportadas**: iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij

### Detección de WAITING

> **Nota**: La detección de WAITING esta actualmente deshabilitada debido a falsos positivos al inicio. Consulta [#140](https://github.com/s-hiraoku/synapse-a2a/issues/140) para más detalles.

Cuando esta habilitada, detecta agentes esperando entrada del usuario (UI de selección, prompts Y/n) usando patrones regex:

- **Gemini**: UI de selección `● 1. Option`, prompts `Allow execution`
- **Claude**: Cursor `❯ Option`, checkboxes `☐/☑`, prompts `[Y/n]`
- **Codex**: Listas numeradas con indentación
- **OpenCode**: Opciones numeradas, indicadores de selección, prompts `[y/N]`
- **Copilot**: Opciones numeradas, indicadores de selección, prompts `[y/N]` o `(y/n)`

---

## Pruebas

Suite de pruebas completa que verifica el cumplimiento del protocolo A2A:

```bash
# Todas las pruebas
pytest

# Categoría especifica
pytest tests/test_a2a_compat.py -v
pytest tests/test_sender_identification.py -v
```

---

## Configuración (.synapse)

Personaliza variables de entorno e instrucciones iniciales vía `.synapse/settings.json`.

### Ámbitos

| Ámbito | Ruta | Prioridad |
|---------|------|-----------|
| Usuario | `~/.synapse/settings.json` | Baja |
| Proyecto | `./.synapse/settings.json` | Media |
| Local | `./.synapse/settings.local.json` | Alta (recomendado en gitignore) |

Las configuraciones de mayor prioridad sobreescriben las de menor prioridad.

### Configuración

```bash
# Crear directorio .synapse/ (copia todos los archivos de plantilla)
synapse init

# ? Donde quieres crear .synapse/?
#   ❯ Ámbito de usuario (~/.synapse/)
#     Ámbito de proyecto (./.synapse/)
#
# ✔ Creado ~/.synapse

# Restablecer a valores por defecto
synapse reset

# Editar configuración interactivamente (TUI)
synapse config

# Mostrar configuración actual (solo lectura)
synapse config show
synapse config show --scope user
```

`synapse init` copia estos archivos a `.synapse/`:

| Archivo | Descripción |
|---------|-------------|
| `settings.json` | Variables de entorno y configuración de instrucciones iniciales |
| `default.md` | Instrucciones iniciales comunes a todos los agentes |
| `gemini.md` | Instrucciones iniciales especificas de Gemini |
| `file-safety.md` | Instrucciones de Seguridad de Archivos |

### Estructura de settings.json

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_DB_PATH": ".synapse/file_safety.db"
  },
  "instructions": {
    "default": "[SYNAPSE INSTRUCTIONS...]\n...",
    "claude": "",
    "gemini": "",
    "codex": ""
  },
  "approvalMode": "required",
  "a2a": {
    "flow": "auto"
  }
}
```

### Variables de Entorno (env)

| Variable | Descripción | Por defecto |
|----------|-------------|-------------|
| `SYNAPSE_HISTORY_ENABLED` | Habilitar historial de tareas | `true` |
| `SYNAPSE_FILE_SAFETY_ENABLED` | Habilitar seguridad de archivos | `true` |
| `SYNAPSE_FILE_SAFETY_DB_PATH` | Ruta de BD de seguridad de archivos | `.synapse/file_safety.db` |
| `SYNAPSE_FILE_SAFETY_RETENTION_DAYS` | Días de retencion del historial de bloqueos | `30` |
| `SYNAPSE_AUTH_ENABLED` | Habilitar autenticacion de API | `false` |
| `SYNAPSE_API_KEYS` | Claves API (separadas por comas) | - |
| `SYNAPSE_ADMIN_KEY` | Clave de administrador | - |
| `SYNAPSE_ALLOW_LOCALHOST` | Omitir autenticacion para localhost | `true` |
| `SYNAPSE_USE_HTTPS` | Usar HTTPS | `false` |
| `SYNAPSE_WEBHOOK_SECRET` | Secreto de webhook | - |
| `SYNAPSE_WEBHOOK_TIMEOUT` | Timeout de webhook (seg) | `10` |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | Reintentos de webhook | `3` |
| `SYNAPSE_SKILLS_DIR` | Directorio del almacén central de skills | `~/.synapse/skills` |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | Umbral de caracteres para almacenamiento en archivo | `200` |
| `SYNAPSE_LONG_MESSAGE_TTL` | TTL para archivos de mensajes (segundos) | `3600` |
| `SYNAPSE_LONG_MESSAGE_DIR` | Directorio para archivos de mensajes | Temp del sistema |
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | Umbral para cambio automático a archivo temporal (bytes) | `102400` |

### Configuración de Comunicación A2A (a2a)

| Configuración | Valor | Descripción |
|---------------|-------|-------------|
| `flow` | `roundtrip` | Siempre esperar resultado |
| `flow` | `oneway` | Siempre solo reenviar (no esperar) |
| `flow` | `auto` | Controlado por banderas; si se omite, espera por defecto |

### Modo de Aprobación (approvalMode)

Controla si mostrar un prompt de confirmación antes de enviar instrucciones iniciales.

| Configuración | Descripción |
|---------------|-------------|
| `required` | Mostrar prompt de aprobacion al inicio (por defecto) |
| `auto` | Enviar instrucciones automáticamente sin solicitar |

Cuando esta configurado como `required`, verás un prompt como:

```
[Synapse] Agent: synapse-claude-8100 | Port: 8100
[Synapse] Initial instructions will be sent to configure A2A communication.

Proceed? [Y/n/s(skip)]:
```

Opciones:
- **Y** (o Enter): Enviar instrucciones iniciales e iniciar agente
- **n**: Abortar inicio
- **s**: Iniciar agente sin enviar instrucciones iniciales

### Instrucciones Iniciales (instructions)

Personaliza las instrucciones enviadas al inicio del agente:

```json
{
  "instructions": {
    "default": "Instrucciones comunes para todos los agentes",
    "claude": "Instrucciones especificas de Claude (tienen prioridad sobre default)",
    "gemini": "Instrucciones especificas de Gemini",
    "codex": "Instrucciones especificas de Codex"
  }
}
```

**Prioridad**:
1. Configuración especifica del agente (`claude`, `gemini`, `codex`, `opencode`, `copilot`) si existe
2. De lo contrario usar `default`
3. Si ambos estan vacios, no se envian instrucciones iniciales

**Marcadores de posición**:
- `{{agent_id}}` - ID de ejecución (ej., `synapse-claude-8100`)
- `{{port}}` - Número de puerto (ej., `8100`)

Consulta [guides/settings.md](guides/settings.md) para más detalles.

---

## Desarrollo y Publicación

### Publicar en PyPI

Al fusionar un cambio de versión en `pyproject.toml` a `main`, se crean automáticamente el tag de git, GitHub Release y la publicación en PyPI.

```bash
# 1. Actualizar versión en pyproject.toml y CHANGELOG.md
# 2. Crear PR y fusionar a main
# 3. Automatización: tag → GitHub Release → PyPI → Homebrew/Scoop PR
```

### Publicación Manual (Respaldo)

```bash
# Compilar y publicar con uv
uv build
uv publish
```

### Instalación de Usuario

**macOS / Linux / WSL2 (recomendado):**
```bash
pipx install synapse-a2a

# Actualizar
pipx upgrade synapse-a2a

# Desinstalar
pipx uninstall synapse-a2a
```

**Windows (Scoop, experimental — WSL2 requerido para pty):**
```bash
scoop bucket add synapse-a2a https://github.com/s-hiraoku/scoop-synapse-a2a
scoop install synapse-a2a

# Actualizar
scoop update synapse-a2a
```

---

## Limitaciones Conocidas

- **Renderizado TUI**: La visualización puede distorsionarse con CLIs basados en Ink
- **Limitaciones PTY**: Algunas secuencias de entrada especiales no son soportadas
- **Foco de Ghostty**: Ghostty utiliza AppleScript para dirigirse a la ventana o pestaña actualmente enfocada. Si cambia de pestaña mientras se ejecuta un comando `spawn` o `team start`, el agente puede generarse en la pestaña no deseada. Espere a que se complete el comando antes de interactuar con la terminal.
- **Sandbox de Codex**: El sandbox de Codex CLI bloquea el acceso a red, requiriendo configuración para la comunicación entre agentes (ver abajo)

### Comunicación Entre Agentes en Codex CLI

Codex CLI se ejecuta en un sandbox por defecto con acceso a red restringido. Para usar el patron `@agent` para comunicación entre agentes, permite el acceso a red en `~/.codex/config.toml`.

**Configuración Global (aplica a todos los proyectos):**

```toml
# ~/.codex/config.toml

sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true
```

**Configuración por Proyecto:**

```toml
# ~/.codex/config.toml

[projects."/path/to/your/project"]
sandbox_mode = "workspace-write"

[projects."/path/to/your/project".sandbox_workspace_write]
network_access = true
```

Consulta [guides/troubleshooting.md](guides/troubleshooting.md#codex-sandbox-network-error) para más detalles.

---

## Funcionalidades Empresariales

Funcionalidades de seguridad, notificaciones y comunicación de alto rendimiento para entornos de produccion.

### Autenticación por Clave API

```bash
# Iniciar con autenticacion habilitada
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS=<TU_CLAVE_API>
synapse claude

# Solicitud con Clave API
curl -H "X-API-Key: <TU_CLAVE_API>" http://localhost:8100/tasks
```

### Notificaciones Webhook

Envía notificaciones a URLs externas cuando las tareas se completan.

```bash
# Registrar webhook
curl -X POST http://localhost:8100/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-server.com/hook", "events": ["task.completed"]}'
```

| Evento | Descripción |
|--------|-------------|
| `task.completed` | Tarea completada exitosamente |
| `task.failed` | Tarea fallida |
| `task.canceled` | Tarea cancelada |

### Streaming SSE

Recibe la salida de tareas en tiempo real.

```bash
curl -N http://localhost:8100/tasks/{task_id}/subscribe
```

Tipos de eventos:

| Evento | Descripción |
|--------|-------------|
| `output` | Nueva salida CLI |
| `status` | Cambio de estado |
| `done` | Tarea completada (incluye Artifact) |

### Parseo de Salida

Parseo automático de la salida CLI para detección de errores, actualizaciones de estado y generación de Artifacts.

| Funcionalidad | Descripción |
|---------------|-------------|
| Detección de Errores | Detecta `command not found`, `permission denied`, etc. |
| input_required | Detecta prompts de pregunta/confirmación |
| Parser de Salida | Estructura código/archivos/errores |

### Soporte gRPC

Usa gRPC para comunicación de alto rendimiento.

```bash
# Instalar dependencias gRPC
pip install synapse-a2a[grpc]

# gRPC se ejecuta en puerto REST + 1
# REST: 8100 → gRPC: 8101
```

Consulta [guides/enterprise.md](guides/enterprise.md) para más detalles.

---

## Documentación

| Ruta | Contenido |
| ---- | --------- |
| [guides/usage.md](guides/usage.md) | Uso detallado |
| [guides/architecture.md](guides/architecture.md) | Detalles de arquitectura |
| [guides/enterprise.md](guides/enterprise.md) | Funcionalidades empresariales |
| [guides/troubleshooting.md](guides/troubleshooting.md) | Solucion de problemas |
| [docs/file-safety.md](docs/file-safety.md) | Prevencion de conflictos de archivos |
| [docs/project-philosophy.md](docs/project-philosophy.md) | Filosofía de diseño |

---

## Licencia

MIT License

---

## Enlaces Relacionados

- [Claude Code](https://claude.ai/code) - Agente CLI de Anthropic
- [OpenCode](https://opencode.ai/) - Agente de programación IA de código abierto
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli) - Asistente de programación IA de GitHub
- [Google A2A Protocol](https://github.com/google/A2A) - Protocolo Agent-to-Agent
