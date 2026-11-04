// Decides whether a shell command may run. Used by guard-bash.mjs.
//
// "deny" is for what the project says must not happen from an agent at all.
// "ask" is for what needs the developer's approval first. Anything else falls
// through to Claude Code's normal permission flow.
//
// This stops mistakes, not an adversary: a script written to a file and then
// run, a shell variable holding a command, and a git alias are not visible here.

const WRAPPERS = new Set(['command', 'exec', 'nohup', 'time', 'sudo', 'nice', 'builtin', 'then', 'do', 'else', 'if', 'while', 'until', '!'])
const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash', 'ksh'])
const INTERPRETERS = /^(python[\d.]*|py|pypy3?|node|deno|bun|perl|ruby|php)$/
const NODE_PACKAGE_MANAGERS = new Set(['pnpm', 'npm', 'yarn', 'bun'])
const NODE_INSTALL_SUBCOMMANDS = new Set(['add', 'install', 'i', 'ci', 'remove', 'rm', 'uninstall', 'un', 'update', 'up', 'upgrade', 'link', 'dlx', 'create'])
const PACKAGE_RUNNERS = new Set(['npx', 'pnpx', 'bunx', 'uvx'])
const SYSTEM_PACKAGE_MANAGERS = new Set(['pip', 'pip3', 'pipx', 'uv', 'poetry', 'conda', 'mamba', 'choco', 'winget', 'scoop', 'brew', 'apt', 'apt-get'])
const SYSTEM_INSTALL_SUBCOMMANDS = new Set(['install', 'uninstall', 'add', 'remove', 'upgrade', 'update', 'sync', 'pip', 'download'])
const DATABASE_TOOLS = new Set(['alembic', 'psql', 'pg_dump', 'pg_restore', 'pg_dumpall', 'supabase'])
const HTTP_CLIENTS = new Set(['curl', 'wget', 'invoke-webrequest', 'invoke-restmethod', 'iwr', 'irm', 'http', 'https'])
const SEARCH_TOOLS = new Set(['grep', 'egrep', 'fgrep', 'rg', 'findstr', 'select-string'])
const DELETERS = new Set(['rm', 'rmdir', 'rd', 'del', 'erase', 'unlink', 'shred', 'truncate', 'remove-item', 'clear-content'])
const MOVERS = new Set(['mv', 'move', 'ren', 'rename', 'move-item', 'rename-item'])
const COPIERS = new Set(['cp', 'copy', 'copy-item', 'install', 'ln', 'xcopy', 'robocopy'])
const WRITERS = new Set(['tee', 'touch', 'set-content', 'add-content', 'out-file', 'new-item', 'dd', 'chmod', 'chown', 'attrib'])

// Read-only masters and the canonical skill library. .claude/skills holds links
// into that library, so a write through it would land there.
const PROTECTED_PATH = /(^|[\\/\s'"=])(\.agents[\\/]skills|\.claude[\\/]skills|skills-lock\.json|docs[\\/]meesho|docs[\\/]flipkart[\\/]templates)([\\/\s'"]|$)/i
const SECRET_FILE = /(^|[^\w.-])(\.env(\.(?!example\b)[\w-]+)*|\.credentials\.json|dynamic_settings\.json)(?![\w.-])/i
const SECRET_NAME = /\b(SUPABASE_SERVICE_KEY|[A-Z][A-Z0-9_]*(API_KEY|_SECRET|_TOKEN|_PASSWORD))\b/
const PRODUCTION_DATABASE = /\bDATABASE_URL\b/
const SEED_SCRIPT = /seed_pilot_data|[\\/.]seeds?[\\/.]/i
const SAFE_DELETE = /(^|[\\/])(\.next|__pycache__|\.pytest_cache|node_modules|htmlcov)([\\/]|$)|[\\/]Temp[\\/]claude[\\/]|^\/tmp\//i
const LOCAL_BACKEND = /(localhost|127\.0\.0\.1):8000/
const SCRIPTED_GIT = /\bgit\b[^\n]{0,40}\b(commit|push|merge|rebase|reset|clean|stash|add|checkout|restore)\b/
const SCRIPTED_WRITE = /\bopen\s*\([^)]*['"][rbt]*[wax+]|\.(save|write\w*|unlink|rename|replace)\s*\(|\b(rmtree|copyfile|copy2?|move|remove)\s*\(/
const SCRIPTED_DATABASE = /\b(SessionLocal|create_engine|psycopg2|get_db)\b|\bengine\.(connect|begin)\b|\.commit\(\)/
// GET, but it marks drafts "exported" and commits.
const WRITES_ON_GET = /\/meesho\/export\b/

// Subagents may only look at the app. Default deny: a browser tool not listed
// here is refused, including any added later.
const BROWSER_READ_TOOLS = new Set(['tabs_context_mcp', 'tabs_create_mcp', 'tabs_close_mcp', 'read_page', 'get_page_text', 'find', 'read_console_messages', 'read_network_requests', 'list_connected_browsers', 'resize_window'])
const BROWSER_READ_ACTIONS = new Set(['screenshot', 'wait', 'zoom', 'scroll', 'scroll_to', 'hover'])
const FRONTEND_URL = /^(https?:\/\/)?(localhost|127\.0\.0\.1):3000([/?#]|$)/i

const MAX_DEPTH = 6

// backend-engineer needs targeted runs for test-first work. One session at a
// time is enforced below for every agent, this list included.
const TEST_RUNNERS = new Set(['verifier', 'backend-engineer'])

const NEEDS_APPROVAL = 'needs the developer\'s approval'
const BACKEND_START = `Starting the backend runs create_all against the real database, so it ${NEEDS_APPROVAL}.`

// Splits a command the way a POSIX shell would, far enough to see every simple
// command, including ones inside $(...), backticks and heredocs.
export function parseShell(command) {
  const segments = []
  const substitutions = []
  let segment = newSegment()
  let token = null
  let quote = null
  let pendingRedirect = false
  let malformed = false

  function newSegment() {
    return { tokens: [], redirects: [], body: '' }
  }
  function endToken() {
    if (token === null) return
    if (pendingRedirect) segment.redirects.push(token)
    else segment.tokens.push(token)
    pendingRedirect = false
    token = null
  }
  function endSegment() {
    endToken()
    pendingRedirect = false
    if (segment.tokens.length || segment.redirects.length) segments.push(segment)
    segment = newSegment()
  }
  function captureParens(start) {
    let depth = 1
    let i = start
    let inner = null
    for (; i < command.length && depth > 0; i++) {
      const c = command[i]
      if (inner) {
        if (c === inner) inner = null
      } else if (c === "'" || c === '"') {
        inner = c
      } else if (c === '(') {
        depth++
      } else if (c === ')') {
        depth--
      }
    }
    if (depth > 0) malformed = true
    substitutions.push(command.slice(start, depth === 0 ? i - 1 : i))
    return i - 1
  }
  function captureBacktick(start) {
    const end = command.indexOf('`', start)
    if (end === -1) {
      malformed = true
      substitutions.push(command.slice(start))
      return command.length
    }
    substitutions.push(command.slice(start, end))
    return end
  }
  function captureHeredoc(afterOperator) {
    const match = /^-?\s*(['"]?)([\w.-]+)\1/.exec(command.slice(afterOperator))
    if (!match) return afterOperator - 1
    const lineEnd = command.indexOf('\n', afterOperator)
    if (lineEnd === -1) return afterOperator + match[0].length - 1
    const terminator = new RegExp(`^\\s*${match[2].replace(/[.-]/g, '\\$&')}\\s*$`, 'm')
    const rest = command.slice(lineEnd + 1)
    const found = terminator.exec(rest)
    segment.body += found ? rest.slice(0, found.index) : rest
    // Carry on after the heredoc, keeping the tail of the opening line.
    const tail = command.slice(afterOperator + match[0].length, lineEnd)
    command = command.slice(0, afterOperator + match[0].length) + tail + '\n' + (found ? rest.slice(found.index + found[0].length) : '')
    return afterOperator + match[0].length - 1
  }

  for (let i = 0; i < command.length; i++) {
    const c = command[i]
    const next = command[i + 1]

    if (quote === "'") {
      if (c === "'") quote = null
      else token += c
      continue
    }
    if (quote === '"') {
      if (c === '"') quote = null
      else if (c === '\\' && next !== undefined && '"\\$`'.includes(next)) {
        token += next
        i++
      } else if (c === '$' && next === '(') i = captureParens(i + 2)
      else if (c === '`') i = captureBacktick(i + 1)
      else token += c
      continue
    }

    if (c === "'" || c === '"') {
      quote = c
      token ??= ''
    } else if (c === '\\') {
      if (next === '\n') i++
      else token = (token ?? '') + c
    } else if (c === '$' && next === '(') {
      token ??= ''
      i = captureParens(i + 2)
    } else if (c === '`') {
      token ??= ''
      i = captureBacktick(i + 1)
    } else if (c === '#' && token === null) {
      const end = command.indexOf('\n', i)
      i = end === -1 ? command.length : end - 1
    } else if (c === ' ' || c === '\t' || c === '\r') {
      endToken()
    } else if (c === '\n' || c === ';' || c === '|' || c === '(' || c === ')') {
      endSegment()
    } else if (c === '&') {
      if (command[i - 1] !== '>') endSegment()
    } else if (c === '>' || c === '<') {
      if (token !== null && /^\d+$/.test(token)) token = null
      else endToken()
      if (c === '<' && next === '<') {
        const herestring = command[i + 2] === '<'
        if (!herestring) i = captureHeredoc(i + 2)
        else i += 2
      } else if (c === '<' && next === '(') {
        endSegment()
      } else {
        if (next === '>') i++
        if (command[i + 1] === '&') {
          i++
          while (/[\d-]/.test(command[i + 1] ?? '')) i++
        } else {
          pendingRedirect = c === '>'
        }
      }
    } else {
      token = (token ?? '') + c
    }
  }
  if (quote) malformed = true
  endSegment()
  return { segments, substitutions, malformed }
}

function exeName(token) {
  return token.split(/[\\/]/).pop().toLowerCase().replace(/\.(exe|cmd|bat|ps1)$/, '')
}

function stripPrefix(tokens) {
  let rest = tokens
  for (;;) {
    const first = rest[0]
    if (first === undefined) return rest
    const name = exeName(first)
    if (/^[A-Za-z_]\w*=/.test(first)) rest = rest.slice(1)
    else if (WRAPPERS.has(name)) rest = rest.slice(1)
    else if (name === 'env') {
      rest = rest.slice(1)
      while (rest[0] !== undefined && (rest[0].startsWith('-') || /^[A-Za-z_]\w*=/.test(rest[0]))) rest = rest.slice(1)
    } else if (name === 'timeout') {
      rest = rest.slice(1)
      while (rest[0] !== undefined && (rest[0].startsWith('-') || /^[\d.]+[smhd]?$/.test(rest[0]))) rest = rest.slice(1)
    } else if (name === 'xargs') {
      rest = rest.slice(1)
      while (rest[0] !== undefined && rest[0].startsWith('-')) rest = rest.slice(/^-[InLPdEs]$/.test(rest[0]) ? 2 : 1)
    } else return rest
  }
}

function classifyGit(args, report) {
  let i = 0
  while (i < args.length && args[i].startsWith('-')) {
    i += /^(-C|-c|--git-dir|--work-tree|--namespace|--exec-path)$/.test(args[i]) ? 2 : 1
  }
  const sub = args[i]
  const rest = args.slice(i + 1)
  const has = (...flags) => rest.some((a) => flags.includes(a))
  const hasShortFlag = (letter) => rest.some((a) => /^-[a-zA-Z]+$/.test(a) && a.includes(letter))
  const ask = (what) => report('ask', `${what} ${NEEDS_APPROVAL}.`)
  const deny = (what) => report('deny', `${what} can destroy or sweep up existing work, so agents never run it. The developer can run it by hand.`)

  switch (sub) {
    case 'add':
      if (has('-A', '--all', '.', ':/', '-u', '--update', '*') || rest.some((a) => a.endsWith('/.') || a.includes('*'))) deny('Broad staging (git add)')
      else ask('Staging files')
      break
    case 'commit':
      if (has('--all') || hasShortFlag('a')) deny('git commit -a')
      else ask('Committing')
      break
    case 'push':
      if (has('--force', '--force-with-lease', '--mirror', '--delete', '-d') || hasShortFlag('f') || rest.some((a) => a.startsWith('--force') || a.startsWith('+') || a.startsWith(':'))) deny('A forced or deleting push')
      else ask('Pushing')
      break
    case 'reset':
      if (has('--hard', '--merge', '--keep')) deny('git reset with a working-tree mode')
      else ask('git reset')
      break
    case 'clean':
      if (!(has('--dry-run') || hasShortFlag('n'))) deny('git clean')
      break
    case 'stash':
      if (!['list', 'show'].includes(rest[0])) deny('git stash')
      break
    case 'checkout':
      if (has('--', '.', '-f', '--force', '-p', '--patch')) deny('git checkout over working files')
      else ask('Switching branches')
      break
    case 'restore':
      deny('git restore')
      break
    case 'switch':
      if (has('-f', '--force', '--discard-changes')) deny('git switch --discard-changes')
      else ask('Switching branches')
      break
    case 'filter-branch':
    case 'filter-repo':
    case 'update-ref':
    case 'replace':
    case 'gc':
    case 'prune':
      deny(`git ${sub}`)
      break
    case 'reflog':
      if (has('expire', 'delete')) deny('Editing the reflog')
      break
    case 'merge':
    case 'rebase':
    case 'pull':
    case 'cherry-pick':
    case 'revert':
    case 'am':
    case 'apply':
    case 'rm':
    case 'mv':
    case 'submodule':
    case 'notes':
      ask(`git ${sub}`)
      break
    case 'branch':
      if (rest.some((a) => !a.startsWith('-')) || has('-d', '-D', '-m', '-M', '-c', '-C', '-f', '--delete', '--move', '--force')) ask('Changing branches')
      break
    case 'tag':
      if (rest.length && !has('-l', '--list')) ask('Changing tags')
      break
    case 'worktree':
      if (rest[0] !== 'list') ask('Changing worktrees')
      break
    case 'config':
      if (rest.filter((a) => !a.startsWith('-')).length >= 2 || rest.some((a) => /^--(unset|add|replace|rename|remove|edit)/.test(a))) ask('Changing git config')
      break
  }
}

function firstSubcommand(args) {
  for (let i = 0; i < args.length; i++) {
    if (/^(-C|--dir|--prefix|--filter|-F|--cwd|--workspace|-w)$/.test(args[i])) i++
    else if (!args[i].startsWith('-')) return args[i]
  }
  return undefined
}

function classifyProtectedPaths(exe, args, redirects, report) {
  const touch = (paths) => paths.some((p) => PROTECTED_PATH.test(p))
  const deny = () => report('deny', 'That path is read-only for agents: the official templates, .agents/skills, .claude/skills and skills-lock.json.')
  if (touch(redirects)) return deny()
  const operands = args.filter((a) => !a.startsWith('-'))
  if ((DELETERS.has(exe) || MOVERS.has(exe) || WRITERS.has(exe)) && touch(args)) return deny()
  if (COPIERS.has(exe) && operands.length && touch(operands.slice(-1))) return deny()
  if (exe === 'sed' && args.some((a) => /^(-[a-zA-Z]*i|--in-place)/.test(a)) && touch(args)) return deny()
}

function classifyDeletes(exe, args, report) {
  const recursive = args.some((a) => /^-[a-zA-Z]*[rR]/.test(a) || /^(--recursive|\/s|-recurse)$/i.test(a))
  const operands = args.filter((a) => !a.startsWith('-') && !/^\/[a-z]$/i.test(a))
  const sweeping = operands.some((a) => a.includes('*'))
  const unsafe = operands.length === 0 || operands.some((a) => !SAFE_DELETE.test(a))
  if (DELETERS.has(exe) && (recursive || sweeping) && unsafe) {
    report('ask', `A recursive or wildcard delete ${NEEDS_APPROVAL}, because it could remove uncommitted work.`)
  }
}

function classifyHttp(args, report) {
  if (args.some((a) => /supabase\.(co|in)\b/i.test(a))) {
    report('ask', `A request to Supabase reaches a production service and ${NEEDS_APPROVAL}.`)
  }
  const writes = args.some((a, i) => /^(-d|-F|-T|--data.*|--form.*|--json|--upload-file|-Method|-Body)$/i.test(a) || (/^(-X|--request)$/.test(a) && /^(POST|PUT|PATCH|DELETE)$/i.test(args[i + 1] ?? '')) || /^-X(POST|PUT|PATCH|DELETE)$/i.test(a))
  if (args.some((a) => LOCAL_BACKEND.test(a)) && (writes || args.some((a) => WRITES_ON_GET.test(a)))) {
    report('ask', `The local backend uses the real database, so a write request ${NEEDS_APPROVAL}.`)
  }
}

function classifyScript(raw, report) {
  if (SCRIPTED_GIT.test(raw)) report('ask', `Running git from a script ${NEEDS_APPROVAL}.`)
  if (PROTECTED_PATH.test(raw) && SCRIPTED_WRITE.test(raw)) report('deny', 'A script may not write to the official templates or the skill library.')
  if (SECRET_NAME.test(raw)) report('ask', `A script that reads a secret value ${NEEDS_APPROVAL}. Never print secrets.`)
  if (SCRIPTED_DATABASE.test(raw) || LOCAL_BACKEND.test(raw)) report('ask', `A script that talks to the database or the local backend ${NEEDS_APPROVAL}, because both use real data.`)
}

function classifySegment(segment, context, depth) {
  const { report } = context
  const tokens = stripPrefix(segment.tokens)
  const { redirects, body } = segment

  if (redirects.some((r) => SECRET_FILE.test(r))) report('deny', 'Writing to .env or a credentials file is not allowed from an agent.')
  if (tokens.length === 0) {
    classifyProtectedPaths('', [], redirects, report)
    return
  }

  const exe = exeName(tokens[0])
  const args = tokens.slice(1)
  const recurse = (text) => classifyCommand(text, context, depth + 1)

  if (SHELLS.has(exe)) {
    const flag = args.findIndex((a) => /^-[a-z]*c$/.test(a))
    if (flag !== -1 && args[flag + 1] !== undefined) recurse(args[flag + 1])
    if (body) recurse(body)
    return
  }
  if (exe === 'cmd') {
    const flag = args.findIndex((a) => /^\/[ck]$/i.test(a))
    if (flag !== -1) recurse(args.slice(flag + 1).join(' '))
    return
  }
  if (exe === 'powershell' || exe === 'pwsh') {
    const flag = args.findIndex((a) => /^-(c|command)$/i.test(a))
    if (flag !== -1) recurse(args.slice(flag + 1).join(' '))
    return
  }
  if (exe === 'eval') {
    recurse(args.join(' '))
    return
  }
  if (exe === 'find') {
    const flag = args.findIndex((a) => /^-(exec|execdir|ok|okdir)$/.test(a))
    if (flag !== -1) classifySegment({ tokens: args.slice(flag + 1).filter((a) => a !== ';' && a !== '+'), redirects: [], body: '' }, context, depth + 1)
    if (args.includes('-delete')) report('ask', `find -delete ${NEEDS_APPROVAL}.`)
    return
  }

  // Secrets. A search pattern is not a file path, so grep ".env" stays allowed.
  if (exe !== 'git' && exe !== 'ls' && exe !== 'test' && exe !== '[') {
    let scanned = args
    if (SEARCH_TOOLS.has(exe)) {
      const pattern = args.findIndex((a) => !a.startsWith('-'))
      scanned = args.filter((_, i) => i !== pattern)
    }
    if (scanned.some((a) => SECRET_FILE.test(a)) || SECRET_FILE.test(body)) {
      report('deny', 'Agents never read .env or credential files. Use .env.example for the variable names, and the Grep tool for code search.')
    }
  }

  if (!SEARCH_TOOLS.has(exe) && exe !== 'git' && exe !== 'echo' && (args.some((a) => PRODUCTION_DATABASE.test(a)) || PRODUCTION_DATABASE.test(body))) {
    report('ask', `Using DATABASE_URL touches the production database and ${NEEDS_APPROVAL}. Tests use TEST_DATABASE_URL.`)
  }

  if (exe === 'git') classifyGit(args, report)
  else if (NODE_PACKAGE_MANAGERS.has(exe)) {
    const sub = firstSubcommand(args)
    if (NODE_INSTALL_SUBCOMMANDS.has(sub) || (args.length === 0 && exe !== 'npm')) report('ask', `Installing or changing dependencies ${NEEDS_APPROVAL}.`)
  } else if (PACKAGE_RUNNERS.has(exe)) {
    report('ask', `${exe} can download and run packages, so it ${NEEDS_APPROVAL}.`)
  } else if (SYSTEM_PACKAGE_MANAGERS.has(exe)) {
    if (SYSTEM_INSTALL_SUBCOMMANDS.has(firstSubcommand(args))) report('ask', `Installing or changing dependencies ${NEEDS_APPROVAL}.`)
  } else if (DATABASE_TOOLS.has(exe)) {
    report('ask', `${exe} touches the database schema or a production service, so it ${NEEDS_APPROVAL}.`)
  } else if (exe === 'uvicorn') {
    report('ask', BACKEND_START)
  } else if (exe === 'claude') {
    if (/^(plugin|plugins|mcp)$/.test(args[0] ?? '') && !/^(list|details|get|--help|-h)$/.test(args[1] ?? '') && !(args[1] === 'marketplace' && args[2] === 'list')) {
      report('ask', `Changing plugins or MCP servers ${NEEDS_APPROVAL}.`)
    }
  } else if (HTTP_CLIENTS.has(exe)) {
    classifyHttp(args, report)
  }

  if (INTERPRETERS.test(exe)) {
    const module = args[args.indexOf('-m') + 1]
    if (args.includes('-m') && (module === 'pip' || module === 'ensurepip')) {
      if (SYSTEM_INSTALL_SUBCOMMANDS.has(args[args.indexOf('-m') + 2]) || module === 'ensurepip') report('ask', `Installing or changing dependencies ${NEEDS_APPROVAL}.`)
    }
    if (args.includes('-m') && module === 'alembic') report('ask', `alembic touches the database schema, so it ${NEEDS_APPROVAL}.`)
    if (args.includes('-m') && module === 'uvicorn') report('ask', BACKEND_START)
    if (args.includes('-m') && /^py\.?test$/.test(module ?? '')) context.runsPytest = true
    if (args.some((a) => SEED_SCRIPT.test(a) && !a.includes('\n'))) report('ask', `The seed script writes to the application database and ${NEEDS_APPROVAL}.`)
    const inline = args.findIndex((a) => /^-[a-z]*[cep]$/.test(a))
    const scriptText = (inline !== -1 ? (args[inline + 1] ?? '') : '') + '\n' + body
    if (scriptText.trim()) classifyScript(scriptText, report)
  }
  if (exe === 'pytest' || exe === 'py.test') context.runsPytest = true

  classifyProtectedPaths(exe, args, redirects, report)
  classifyDeletes(exe, args, report)
}

function classifyCommand(command, context, depth) {
  if (depth > MAX_DEPTH) {
    context.report('ask', `That command is nested too deeply to check, so it ${NEEDS_APPROVAL}.`)
    return
  }
  const { segments, substitutions, malformed } = parseShell(command)
  if (malformed) context.report('ask', `That command could not be parsed, so it ${NEEDS_APPROVAL}.`)
  for (const segment of segments) classifySegment(segment, context, depth)
  for (const text of substitutions) classifyCommand(text, context, depth + 1)
}

// Returns { decision: 'deny' | 'ask' | 'allow', reason } for a Claude in Chrome tool.
// The local app runs on the real database, so a subagent can look but not act.
// The main thread keeps its browser, with the approval rule in orchestration.md.
export function decideBrowser(toolName, input, agentType) {
  const tool = toolName.split('__').pop()
  const url = String(input?.url ?? '')
  const refused = (what) => ({ decision: 'deny', reason: `${what} is refused for subagents, because the local app uses the real database. Report it as NOT VERIFIED and let the main thread ask the developer.` })

  if (tool === 'navigate' && WRITES_ON_GET.test(url)) {
    if (agentType) return refused('Opening the Meesho export URL')
    return { decision: 'ask', reason: `Opening the Meesho export URL marks drafts "exported" in the real database, so it ${NEEDS_APPROVAL}.` }
  }
  if (!agentType) return { decision: 'allow', reason: '' }

  if (BROWSER_READ_TOOLS.has(tool)) return { decision: 'allow', reason: '' }
  if (tool === 'computer' && BROWSER_READ_ACTIONS.has(input?.action)) return { decision: 'allow', reason: '' }
  if (tool === 'navigate') {
    if (FRONTEND_URL.test(url) || url === 'about:blank') return { decision: 'allow', reason: '' }
    return refused(`Navigating to ${url.slice(0, 60)}`)
  }
  return refused(`Browser action ${tool}${input?.action ? ` (${input.action})` : ''}`)
}

// Returns { decision: 'deny' | 'ask' | 'allow', reason }.
// isPytestRunning returns true, false, or null when it can't tell.
export function decide(command, { agentType, isPytestRunning, claimPytest }) {
  const findings = []
  const context = {
    runsPytest: false,
    report: (level, reason) => findings.push({ level, reason }),
  }
  classifyCommand(command, context, 0)

  const denied = findings.find((f) => f.level === 'deny')
  if (denied) return { decision: 'deny', reason: denied.reason }
  const asked = findings.find((f) => f.level === 'ask')
  // A prompt raised by a background agent is easy to accept without context, so
  // approval only ever happens on the main thread.
  if (asked && agentType) return { decision: 'deny', reason: `${asked.reason} Subagents can't get approval: stop and report this to the main thread, which will ask the developer.` }
  if (asked) return { decision: 'ask', reason: asked.reason }

  if (context.runsPytest) {
    if (agentType && !TEST_RUNNERS.has(agentType)) {
      return { decision: 'deny', reason: `Only the main thread, verifier and backend-engineer run pytest, because test sessions share TEST_DATABASE_URL and drop each other's tables. Report back to the main thread instead (agent: ${agentType}).` }
    }
    const running = isPytestRunning()
    if (running === null) return { decision: 'ask', reason: 'Could not check for a running pytest session. A second session would drop the first one\'s tables.' }
    if (running || !claimPytest()) {
      return { decision: 'deny', reason: 'Another pytest session is running. Two sessions share TEST_DATABASE_URL and drop each other\'s tables. Wait for it to finish.' }
    }
  }
  return { decision: 'allow', reason: '' }
}
