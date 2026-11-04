// Run with: node --test ".claude/hooks/*.test.mjs"

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { decide, decideBrowser, parseShell } from './guard-rules.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const idle = { isPytestRunning: () => false, claimPytest: () => true }
const verdict = (command, options = {}) => decide(command, { ...idle, ...options }).decision

function table(name, expected, commands) {
  for (const command of commands) {
    test(`${name}: ${JSON.stringify(command)}`, () => {
      assert.equal(verdict(command), expected)
    })
  }
}

table('commits need approval', 'ask', [
  'git commit -m "x"',
  'git -C . commit -m x',
  'git -C "D:/Education/Work/ListingPilot" commit -m x',
  'git -c user.name=x commit -m x',
  'git --no-pager commit -m x',
  '/usr/bin/git commit -m x',
  'git.exe commit -m x',
  '"git" commit -m x',
  "g'i't commit -m x",
  'FOO=1 git commit -m x',
  'env FOO=1 git commit -m x',
  'cd backend && git commit -m x',
  'echo hi; git commit -m x',
  'true || git commit -m x',
  'echo hi | git commit -F -',
  '(git commit -m x)',
  'if true; then git commit -m x; fi',
  'bash -c "git commit -m x"',
  "sh -c 'git commit -m x'",
  'bash -lc "git commit -m x"',
  'cmd /c git commit -m x',
  'powershell -Command "git commit -m x"',
  'pwsh -c "git commit -m x"',
  'eval "git commit -m x"',
  'echo $(git commit -m x)',
  'echo "$(git commit -m x)"',
  'echo `git commit -m x`',
  'xargs git commit -m x',
  'find . -name x -exec git commit -m x \\;',
  'timeout 5 git commit -m x',
  'nohup git commit -m x',
  'git commit --amend',
  'python -c "import subprocess; subprocess.run([\'git\', \'commit\', \'-m\', \'x\'])"',
  'node -e "require(\'child_process\').execSync(\'git commit -m x\')"',
  ".venv/Scripts/python.exe - <<'EOF'\nimport os\nos.system('git commit -m x')\nEOF",
])

table('other history changes need approval', 'ask', [
  'git push',
  'git push origin main',
  'git merge feature',
  'git rebase main',
  'git pull',
  'git cherry-pick abc',
  'git revert abc',
  'git branch -D old',
  'git branch new',
  'git switch main',
  'git checkout main',
  'git reset HEAD~1',
  'git add backend/app/main.py',
  'git rm backend/x.py',
  'git tag v1',
  'git worktree add ../x',
  'git config core.hooksPath x',
])

table('work-destroying git is denied', 'deny', [
  'git add -A',
  'git add --all',
  'git add .',
  'git add -u',
  'git add backend/*.py',
  'git -C . add -A',
  'bash -c "git add ."',
  'git commit -am "x"',
  'git commit -a -m x',
  'git commit --all -m x',
  'git reset --hard',
  'git reset --hard HEAD',
  'git -C . reset --hard',
  'git clean -fd',
  'git clean -fdX',
  'git stash',
  'git stash push',
  'git stash pop',
  'git stash drop',
  'git stash clear',
  'git checkout -- backend/app/main.py',
  'git checkout .',
  'git checkout -f main',
  'git restore backend/app/main.py',
  'git restore --staged .',
  'git push --force',
  'git push -f origin main',
  'git push --force-with-lease',
  'git push origin :main',
  'git push origin +main',
  'git filter-branch',
  'git update-ref HEAD abc',
])

table('reading git state is untouched', 'allow', [
  'git status',
  'git status --short',
  'git diff',
  'git diff --stat -- AGENTS.md',
  'git log --oneline -5',
  'git show HEAD',
  'git ls-files',
  'git rev-parse HEAD',
  'git blame AGENTS.md',
  'git stash list',
  'git stash show',
  'git branch',
  'git branch -a',
  'git branch --show-current',
  'git tag',
  'git tag -l',
  'git worktree list',
  'git config core.symlinks',
  'git config --get user.name',
  'git clean -n',
  'git clean --dry-run',
  'git fetch',
  'git check-ignore .env',
])

table('dependencies need approval', 'ask', [
  'pnpm add lodash',
  'pnpm install',
  'pnpm i',
  'pnpm -C frontend add lodash',
  'pnpm --dir frontend add lodash',
  'cd frontend; pnpm add lodash',
  'pnpm dlx create-next-app',
  'npm install',
  'npm i lodash',
  'npm --prefix frontend install',
  'yarn add lodash',
  'yarn',
  'bun add x',
  'npx skills add foo',
  'pnpx x',
  'pip install requests',
  'pip3 install requests',
  '.venv/Scripts/pip.exe install requests',
  'python -m pip install requests',
  '.venv\\Scripts\\python.exe -m pip install requests',
  '.venv/Scripts/python.exe -m pip uninstall requests',
  'uv add requests',
  'poetry add requests',
  'winget install x',
  'claude plugin install x',
  'claude mcp add x',
])

table('schema and production need approval', 'ask', [
  'alembic upgrade head',
  'alembic revision -m x',
  '.venv/Scripts/alembic.exe upgrade head',
  '.venv/Scripts/python.exe -m alembic upgrade head',
  'psql "$DATABASE_URL"',
  'supabase db push',
  'pg_dump x',
  '.venv/Scripts/python.exe backend/app/seeds/seed_pilot_data.py',
  'python -m app.seeds.seed_pilot_data',
  'python -c "import os; print(os.environ[\'DATABASE_URL\'])"',
  'curl https://abc.supabase.co/rest/v1/products',
  'curl -X POST http://localhost:8000/api/v1/drafts',
  'curl -XDELETE http://127.0.0.1:8000/api/v1/drafts/1',
  'curl -d "a=1" http://localhost:8000/api/v1/drafts',
  'python -c "from app.core.config import settings; print(settings.SUPABASE_SERVICE_KEY)"',
  'python -c "print(settings.GROQ_API_KEY)"',
  '.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000',
  'uvicorn app.main:app --port 8000',
  'curl http://localhost:8000/api/v1/drafts/meesho/export?product_ids=1',
  'curl -s "http://127.0.0.1:8000/api/v1/drafts/meesho/export"',
  'python -c "import requests; requests.post(\'http://localhost:8000/api/v1/drafts\')"',
  'python -c "from app.core.database import SessionLocal; db = SessionLocal(); db.commit()"',
  ".venv/Scripts/python.exe - <<'EOF'\nimport psycopg2\nEOF",
])

table('secrets stay unread', 'deny', [
  'cat .env',
  'cat ./.env',
  'head -5 .env',
  'sed -E "s/=.*//" .env',
  'grep KEY .env',
  'rg KEY .env',
  'type .env',
  'Get-Content .env',
  'cp .env /tmp/x',
  'cat frontend/.env.local',
  'less backend/.env',
  'cat < .env',
  'python -c "print(open(\'.env\').read())"',
  'bash -c "cat .env"',
  'cat ~/.claude/.credentials.json',
  'cat backend/app/data/dynamic_settings.json',
  'echo x >> .env',
  'echo x > .env.local',
])

table('protected paths stay read-only', 'deny', [
  'rm docs/meesho/template.xlsx',
  'rm -rf docs/meesho',
  'mv docs/meesho/a.xlsx b.xlsx',
  'cp x.xlsx docs/meesho/a.xlsx',
  'echo x > docs/meesho/a.txt',
  'sed -i "s/a/b/" docs/flipkart/templates/a.csv',
  'tee docs/meesho/a.txt',
  'rm -rf .agents/skills',
  'rm -rf .agents/skills/tdd',
  'echo x >> .agents/skills/tdd/SKILL.md',
  'sed -i "s/a/b/" .agents/skills/tdd/SKILL.md',
  'rm -rf .claude/skills',
  'echo x > .claude/skills/tdd/SKILL.md',
  'rm skills-lock.json',
  'echo {} > skills-lock.json',
  'python -c "wb.save(\'docs/meesho/a.xlsx\')"',
  'python -c "open(\'docs/meesho/a.txt\', \'w\').write(\'x\')"',
  'python -c "open(\'docs/meesho/a.txt\', \'ab\')"',
  'python -c "import shutil; shutil.copy(\'x\', \'docs/meesho/a.xlsx\')"',
  'python -c "import os; os.remove(\'docs/meesho/a.xlsx\')"',
  'python -c "from pathlib import Path; Path(\'docs/meesho/a.txt\').write_text(\'x\')"',
  ".venv/Scripts/python.exe - <<'EOF'\nimport openpyxl\nwb.save('docs/meesho/out.xlsx')\nEOF",
])

table('risky deletes need approval', 'ask', [
  'rm -rf backend',
  'rm -rf frontend/app',
  'rm -r docs',
  'rm -fr backend/app',
  'rm *',
  'rm -rf "$TARGET"',
  'find . -name "*.py" -delete',
  'powershell -Command "Remove-Item -Recurse backend"',
])

table('routine work runs freely', 'allow', [
  'ls -la',
  'cat README.md',
  'cat .env.example',
  'grep -n "\\.env" backend/app/core/config.py',
  'grep -rn DATABASE_URL backend/tests/conftest.py',
  'rg ".env" docs',
  'ls -a .env',
  'echo "git commit is not run here"',
  'grep "git push" AGENTS.md',
  'pnpm dev',
  'pnpm build',
  'pnpm run lint',
  'pnpm --version',
  'npm run build',
  'node --test ".claude/hooks/*.test.mjs"',
  'node --version',
  '.venv/Scripts/python.exe -m pip list',
  '.venv/Scripts/python.exe -m pip show openpyxl',
  'pip list',
  'curl http://localhost:8000/health',
  'curl -s http://localhost:8000/api/v1/drafts',
  'rm -rf frontend/.next',
  'python -c "print(open(\'docs/meesho/a.txt\').read())"',
  'python -c "print(open(\'docs/meesho/a.txt\', \'rb\').read())"',
  ".venv/Scripts/python.exe - <<'EOF'\nimport openpyxl\nwb = openpyxl.load_workbook('docs/meesho/t.xlsx', read_only=True)\nprint(wb.sheetnames)\nEOF",
  'rm -rf backend/app/__pycache__',
  'rm -rf C:/Users/Nishant/AppData/Local/Temp/claude/abc/scratchpad/probe',
  'rm notes.tmp',
  'cp docs/meesho/template.xlsx /tmp/copy.xlsx',
  'claude plugin list',
  'claude plugin details pstack',
  "cat > notes.md <<'EOF'\ngit commit -m x\nrm -rf backend\nEOF",
  'echo "a; git commit"',
  "echo 'a && git push'",
])

test('anything needing approval is refused for subagents, never prompted', () => {
  const needsApproval = [
    'git commit -m x',
    'git push',
    'pnpm add lodash',
    'npx --version',
    'curl -X POST http://localhost:8000/api/v1/drafts',
    'curl http://localhost:8000/api/v1/drafts/meesho/export',
    '.venv/Scripts/python.exe -m uvicorn --version',
    'alembic upgrade head',
    'rm -rf backend',
  ]
  for (const command of needsApproval) {
    assert.equal(verdict(command), 'ask', command)
    for (const agentType of ['verifier', 'backend-engineer', 'frontend-engineer', 'general-purpose']) {
      assert.equal(verdict(command, { agentType }), 'deny', `${agentType}: ${command}`)
    }
  }
  assert.equal(verdict('git status', { agentType: 'verifier' }), 'allow')
})

test('pytest runs on the main thread when idle', () => {
  assert.equal(verdict('.venv/Scripts/python.exe -m pytest backend/tests -q'), 'allow')
  assert.equal(verdict('.venv\\Scripts\\python.exe -m pytest backend/tests -q'), 'allow')
  assert.equal(verdict('pytest backend/tests'), 'allow')
})

test('pytest is limited to the main thread and the named test runners', () => {
  const command = '.venv/Scripts/python.exe -m pytest backend/tests -q'
  assert.equal(verdict(command, { agentType: 'verifier' }), 'allow')
  assert.equal(verdict(command, { agentType: 'backend-engineer' }), 'allow')
  for (const agentType of ['frontend-engineer', 'database-supabase', 'architect', 'general-purpose', 'Explore', 'pstack:poteto-agent']) {
    assert.equal(verdict(command, { agentType }), 'deny', agentType)
  }
  assert.equal(verdict('bash -c "pytest backend/tests"', { agentType: 'frontend-engineer' }), 'deny')
  assert.equal(verdict('cd backend && python -m pytest', { agentType: 'frontend-engineer' }), 'deny')
})

test('a second pytest session is denied for every agent', () => {
  const command = '.venv/Scripts/python.exe -m pytest backend/tests -q'
  assert.equal(verdict(command, { isPytestRunning: () => true }), 'deny')
  assert.equal(verdict(command, { agentType: 'verifier', isPytestRunning: () => true }), 'deny')
  assert.equal(verdict(command, { agentType: 'backend-engineer', isPytestRunning: () => true }), 'deny')
  assert.equal(verdict(command, { claimPytest: () => false }), 'deny')
})

test('an unknown pytest state asks rather than guesses', () => {
  assert.equal(verdict('pytest', { isPytestRunning: () => null }), 'ask')
})

test('the running-session check only happens for pytest', () => {
  const fail = () => assert.fail('should not be called')
  assert.equal(verdict('ls', { isPytestRunning: fail, claimPytest: fail }), 'allow')
})

test('deny beats ask in one command', () => {
  assert.equal(verdict('git commit -m x && git reset --hard'), 'deny')
})

test('an unparseable command asks', () => {
  assert.equal(verdict('echo "unterminated'), 'ask')
  assert.equal(verdict('echo $(git status'), 'ask')
})

test('deep nesting asks', () => {
  let command = 'ls'
  for (let i = 0; i < 9; i++) command = `bash -c ${JSON.stringify(command)}`
  assert.equal(verdict(command), 'ask')
})

test('parseShell keeps heredoc bodies out of the command stream', () => {
  const { segments } = parseShell("cat > a.md <<'EOF'\ngit push\nEOF\nls")
  assert.deepEqual(segments.map((s) => s.tokens[0]), ['cat', 'ls'])
  assert.match(segments[0].body, /git push/)
})

const chrome = (tool) => `mcp__claude-in-chrome__${tool}`
const browser = (tool, input, agentType) => decideBrowser(chrome(tool), input, agentType).decision

for (const agentType of ['verifier', 'general-purpose', 'frontend-engineer']) {
  test(`${agentType} can look at the app`, () => {
    for (const tool of ['tabs_context_mcp', 'tabs_create_mcp', 'read_page', 'get_page_text', 'find', 'read_console_messages', 'read_network_requests']) {
      assert.equal(browser(tool, {}, agentType), 'allow', tool)
    }
    for (const action of ['screenshot', 'wait', 'zoom', 'scroll', 'hover']) {
      assert.equal(browser('computer', { action }, agentType), 'allow', action)
    }
    for (const url of ['http://localhost:3000', 'http://localhost:3000/', 'localhost:3000/settings', 'http://127.0.0.1:3000/?tab=1', 'about:blank']) {
      assert.equal(browser('navigate', { url }, agentType), 'allow', url)
    }
  })

  test(`${agentType} cannot act on the app`, () => {
    for (const action of ['left_click', 'right_click', 'double_click', 'triple_click', 'type', 'key', 'left_click_drag']) {
      assert.equal(browser('computer', { action }, agentType), 'deny', action)
    }
    assert.equal(browser('computer', {}, agentType), 'deny')
    for (const tool of ['form_input', 'javascript_tool', 'file_upload', 'upload_image', 'browser_batch', 'shortcuts_execute', 'switch_browser', 'a_tool_added_later']) {
      assert.equal(browser(tool, {}, agentType), 'deny', tool)
    }
  })

  test(`${agentType} cannot reach the backend or other sites`, () => {
    for (const url of [
      'http://localhost:8000/api/v1/drafts/meesho/export?product_ids=1',
      'http://localhost:3000/api/v1/drafts/meesho/export',
      'http://localhost:8000/health',
      'http://localhost:30000',
      'http://localhost:3000.evil.example',
      'https://supplier.meesho.com',
      'https://supabase.com/dashboard',
      'back',
    ]) {
      assert.equal(browser('navigate', { url }, agentType), 'deny', url)
    }
  })
}

test('the main thread needs approval for the export URL and keeps its browser otherwise', () => {
  assert.equal(browser('navigate', { url: 'http://localhost:8000/api/v1/drafts/meesho/export?product_ids=1' }), 'ask')
  assert.equal(browser('navigate', { url: 'http://localhost:3000' }), 'allow')
  assert.equal(browser('computer', { action: 'left_click' }), 'allow')
})

test('the browser hook entry returns a deny for a subagent click', () => {
  const input = JSON.stringify({ tool_name: chrome('computer'), tool_input: { action: 'left_click' }, agent_type: 'verifier' })
  const result = spawnSync(process.execPath, [path.join(here, 'guard-browser.mjs')], { input, encoding: 'utf8' })
  assert.equal(result.status, 0)
  assert.equal(JSON.parse(result.stdout).hookSpecificOutput.permissionDecision, 'deny')
})

test('bad browser hook input exits non-zero so onFailure can block', () => {
  const result = spawnSync(process.execPath, [path.join(here, 'guard-browser.mjs')], { input: 'not json', encoding: 'utf8' })
  assert.notEqual(result.status, 0)
})

test('the hook entry returns a deny for Claude Code', () => {
  const input = JSON.stringify({ tool_name: 'Bash', tool_input: { command: 'git reset --hard' } })
  const result = spawnSync(process.execPath, [path.join(here, 'guard-bash.mjs')], { input, encoding: 'utf8' })
  assert.equal(result.status, 0)
  const output = JSON.parse(result.stdout).hookSpecificOutput
  assert.equal(output.hookEventName, 'PreToolUse')
  assert.equal(output.permissionDecision, 'deny')
})

test('the hook entry returns ask for Claude Code', () => {
  const input = JSON.stringify({ tool_name: 'Bash', tool_input: { command: 'git commit -m x' } })
  const result = spawnSync(process.execPath, [path.join(here, 'guard-bash.mjs')], { input, encoding: 'utf8' })
  assert.equal(JSON.parse(result.stdout).hookSpecificOutput.permissionDecision, 'ask')
})

test('the hook entry stays silent on routine commands', () => {
  const input = JSON.stringify({ tool_name: 'Bash', tool_input: { command: 'git status' } })
  const result = spawnSync(process.execPath, [path.join(here, 'guard-bash.mjs')], { input, encoding: 'utf8' })
  assert.equal(result.status, 0)
  assert.equal(result.stdout, '')
})

test('bad hook input exits non-zero so onFailure can block', () => {
  const result = spawnSync(process.execPath, [path.join(here, 'guard-bash.mjs')], { input: 'not json', encoding: 'utf8' })
  assert.notEqual(result.status, 0)
})
