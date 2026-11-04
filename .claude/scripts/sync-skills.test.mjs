// Run with: node --test ".claude/scripts/*.test.mjs"
// Each test builds a throwaway repo in the system temp folder, so the real
// .agents/skills/ and .claude/skills/ are never involved.

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, test } from 'node:test'
import { fileURLToPath } from 'node:url'

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'sync-skills.mjs')
const fixtures = []

function makeRepo(skills = { alpha: 'obra/superpowers', beta: 'obra/superpowers', plugged: 'backnotprop/pstack' }) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-skills-'))
  fixtures.push(root)
  fs.mkdirSync(path.join(root, '.claude', 'scripts'), { recursive: true })
  fs.copyFileSync(SCRIPT, path.join(root, '.claude', 'scripts', 'sync-skills.mjs'))
  const lock = { version: 1, skills: {} }
  for (const [name, source] of Object.entries(skills)) {
    lock.skills[name] = { source }
    const dir = path.join(root, '.agents', 'skills', name)
    fs.mkdirSync(path.join(dir, 'references'), { recursive: true })
    fs.writeFileSync(path.join(dir, 'SKILL.md'), `---\nname: ${name}\n---\nbody ${name}\n`)
    fs.writeFileSync(path.join(dir, 'references', 'note.md'), 'keep me\n')
  }
  fs.writeFileSync(path.join(root, 'skills-lock.json'), JSON.stringify(lock))
  return root
}

function sync(root, ...args) {
  return spawnSync(process.execPath, [path.join(root, '.claude', 'scripts', 'sync-skills.mjs'), ...args], { encoding: 'utf8' })
}

function libraryHash(root) {
  const hash = crypto.createHash('sha256')
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(dir, entry.name)
      hash.update(path.relative(root, p))
      if (entry.isDirectory()) walk(p)
      else hash.update(fs.readFileSync(p))
    }
  }
  walk(path.join(root, '.agents', 'skills'))
  return hash.digest('hex')
}

const linkPath = (root, name) => path.join(root, '.claude', 'skills', name)
const isLink = (p) => {
  try {
    return fs.lstatSync(p).isSymbolicLink()
  } catch {
    return false
  }
}
const junction = (target, p) => fs.symlinkSync(target, p, 'junction')

afterEach(() => {
  for (const root of fixtures.splice(0)) {
    const skillsDir = path.join(root, '.claude', 'skills')
    // Unlink first so the cleanup below can't walk through a link.
    if (fs.existsSync(skillsDir) && !isLink(skillsDir)) {
      for (const name of fs.readdirSync(skillsDir)) {
        const p = path.join(skillsDir, name)
        if (isLink(p)) fs.unlinkSync(p)
      }
    }
    if (isLink(skillsDir)) fs.unlinkSync(skillsDir)
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('links skills and skips plugin-provided sources', () => {
  const root = makeRepo()
  const result = sync(root)
  assert.equal(result.status, 0, result.stdout + result.stderr)
  assert.ok(isLink(linkPath(root, 'alpha')))
  assert.ok(isLink(linkPath(root, 'beta')))
  assert.equal(fs.existsSync(linkPath(root, 'plugged')), false)
  assert.match(fs.readFileSync(path.join(linkPath(root, 'alpha'), 'SKILL.md'), 'utf8'), /body alpha/)
})

test('a second run changes nothing and prints nothing', () => {
  const root = makeRepo()
  sync(root)
  const result = sync(root)
  assert.equal(result.status, 0)
  assert.equal(result.stdout, '')
})

test('removing a stale link leaves the canonical skill intact', () => {
  const root = makeRepo()
  sync(root)
  const before = libraryHash(root)
  const lockPath = path.join(root, 'skills-lock.json')
  const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'))
  delete lock.skills.beta
  fs.writeFileSync(lockPath, JSON.stringify(lock))

  const result = sync(root)
  assert.equal(result.status, 0, result.stdout)
  assert.equal(fs.existsSync(linkPath(root, 'beta')), false)
  assert.equal(libraryHash(root), before)
})

test('never touches the library across create, stale and recovery runs', () => {
  const root = makeRepo()
  const before = libraryHash(root)
  sync(root)
  fs.unlinkSync(linkPath(root, 'alpha'))
  sync(root)
  sync(root, '--check')
  assert.equal(libraryHash(root), before)
})

test('leaves a link that points outside the library and reports it', () => {
  const root = makeRepo()
  const elsewhere = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-outside-'))
  fixtures.push(elsewhere)
  fs.writeFileSync(path.join(elsewhere, 'precious.txt'), 'data')
  fs.mkdirSync(path.join(root, '.claude', 'skills'))
  junction(elsewhere, linkPath(root, 'alpha'))

  const result = sync(root)
  assert.equal(result.status, 1)
  assert.match(result.stdout, /points outside/)
  assert.ok(isLink(linkPath(root, 'alpha')))
  assert.ok(fs.existsSync(path.join(elsewhere, 'precious.txt')))
})

test('leaves a real folder that uses a wanted name', () => {
  const root = makeRepo()
  const real = linkPath(root, 'alpha')
  fs.mkdirSync(real, { recursive: true })
  fs.writeFileSync(path.join(real, 'SKILL.md'), 'mine\n')

  const result = sync(root)
  assert.equal(result.status, 1)
  assert.match(result.stdout, /real folder/)
  assert.equal(fs.readFileSync(path.join(real, 'SKILL.md'), 'utf8'), 'mine\n')
})

test('refuses to run when .claude/skills is itself a link to the library', () => {
  const root = makeRepo()
  const before = libraryHash(root)
  junction(path.join(root, '.agents', 'skills'), path.join(root, '.claude', 'skills'))

  const result = sync(root)
  assert.equal(result.status, 2)
  assert.match(result.stderr, /is a link/)
  assert.equal(libraryHash(root), before)
})

test('refuses a skill directory that is a link leaving the library', () => {
  const root = makeRepo({ alpha: 'obra/superpowers' })
  const elsewhere = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-outside-'))
  fixtures.push(elsewhere)
  fs.writeFileSync(path.join(elsewhere, 'SKILL.md'), 'x\n')
  const target = path.join(root, '.agents', 'skills', 'alpha')
  fs.rmSync(target, { recursive: true })
  junction(elsewhere, target)

  const result = sync(root)
  assert.equal(result.status, 1)
  assert.match(result.stdout, /not a real directory/)
  assert.equal(fs.existsSync(linkPath(root, 'alpha')), false)
  fs.unlinkSync(target)
})

test('rejects path traversal in lock file names', () => {
  const root = makeRepo()
  const lockPath = path.join(root, 'skills-lock.json')
  const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'))
  lock.skills['../../evil'] = { source: 'obra/superpowers' }
  lock.skills['..\\evil'] = { source: 'obra/superpowers' }
  fs.writeFileSync(lockPath, JSON.stringify(lock))

  const result = sync(root)
  assert.equal(result.status, 1)
  assert.match(result.stdout, /unsafe skill name/)
  assert.equal(fs.existsSync(path.join(root, 'evil')), false)
})

test('recovers from an interrupted run', () => {
  const root = makeRepo()
  sync(root)
  const before = libraryHash(root)
  // A killed run leaves a temp link or an empty directory, under a dead pid.
  const deadPid = 999999
  fs.unlinkSync(linkPath(root, 'beta'))
  junction(path.join(root, '.agents', 'skills', 'beta'), linkPath(root, `.sync-tmp-${deadPid}-beta`))
  fs.mkdirSync(linkPath(root, `.sync-tmp-${deadPid}-gamma`))

  const result = sync(root)
  assert.equal(result.status, 0, result.stdout)
  assert.deepEqual(fs.readdirSync(path.join(root, '.claude', 'skills')).sort(), ['alpha', 'beta'])
  assert.ok(isLink(linkPath(root, 'beta')))
  assert.equal(libraryHash(root), before)
})

test('a non-empty temp directory is reported, never deleted', () => {
  const root = makeRepo()
  sync(root)
  const temp = linkPath(root, '.sync-tmp-999999-odd')
  fs.mkdirSync(temp)
  fs.writeFileSync(path.join(temp, 'file.txt'), 'keep\n')

  const result = sync(root)
  assert.equal(result.status, 1)
  assert.match(result.stdout, /not empty/)
  assert.ok(fs.existsSync(path.join(temp, 'file.txt')))
})

test('a temp entry owned by a live process is left alone', () => {
  const root = makeRepo()
  sync(root)
  const temp = linkPath(root, `.sync-tmp-${process.pid}-busy`)
  fs.mkdirSync(temp)

  const result = sync(root)
  assert.equal(result.status, 0, result.stdout)
  assert.ok(fs.existsSync(temp))
})

test('--check reports drift and changes nothing', () => {
  const root = makeRepo()
  sync(root)
  fs.unlinkSync(linkPath(root, 'alpha'))

  const result = sync(root, '--check')
  assert.equal(result.status, 1)
  assert.match(result.stdout, /missing link alpha/)
  assert.equal(fs.existsSync(linkPath(root, 'alpha')), false)
})

test('two simultaneous runs end in the same correct state', async () => {
  const root = makeRepo()
  const script = path.join(root, '.claude', 'scripts', 'sync-skills.mjs')
  const { spawn } = await import('node:child_process')
  const run = () => new Promise((resolve) => spawn(process.execPath, [script]).on('close', resolve))
  await Promise.all([run(), run(), run()])

  assert.equal(sync(root, '--check').status, 0)
  assert.deepEqual(fs.readdirSync(path.join(root, '.claude', 'skills')).sort(), ['alpha', 'beta'])
})
