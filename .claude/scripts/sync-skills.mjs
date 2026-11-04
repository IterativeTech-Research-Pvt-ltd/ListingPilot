#!/usr/bin/env node
// Exposes skills from .agents/skills/ to Claude Code as links in .claude/skills/.
//
// .agents/skills/ is the canonical library; this script only ever touches link
// entries directly inside .claude/skills/. Windows junctions need no privilege,
// unlike symlinks, and on other platforms Node creates a plain symlink instead.
//
// Safety rules, each enforced in code below and covered by sync-skills.test.mjs:
//   - The only mutating calls are symlink, rename, unlink and a non-recursive
//     rmdir, all on paths whose parent is exactly .claude/skills/.
//   - unlink refuses real directories, so removing a link can't recurse into
//     its target. No recursive delete exists in this file.
//   - A link is created under a temporary name and renamed into place, so a
//     skill name only ever holds a complete link. An interrupted run leaves at
//     most a temporary entry, which the next run clears.
//   - A link or directory this script can't prove it owns is reported and left.
//
// Usage: node .claude/scripts/sync-skills.mjs [--check]
//   --check  Report drift and exit 1 if any, without changing anything.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// These sources reach Claude Code as plugins. Linking them too would list every
// skill twice.
const PLUGIN_SOURCES = new Set(['backnotprop/pstack', 'DietrichGebert/ponytail'])
const SAFE_NAME = /^[a-z0-9][a-z0-9-]*$/
const RESERVED_NAMES = new Set(['synced', 'anthropic-skills'])
const TEMP_PREFIX = '.sync-tmp-'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const canonicalDir = path.join(root, '.agents', 'skills')
const linkDir = path.join(root, '.claude', 'skills')
const checkOnly = process.argv.includes('--check')

const created = []
const removed = []
const problems = []

const fold = (p) => (process.platform === 'win32' ? p.toLowerCase() : p)
const samePath = (a, b) => fold(path.resolve(a)) === fold(path.resolve(b))
const isDirectChild = (child, parent) => samePath(path.dirname(path.resolve(child)), parent)

function lstatOrNull(p) {
  try {
    return fs.lstatSync(p)
  } catch (e) {
    if (e.code === 'ENOENT') return null
    throw e
  }
}

function fail(message) {
  console.error(`[sync-skills] ${message}`)
  process.exit(2)
}

// Every mutation goes through here, so nothing outside .claude/skills/ can change.
function assertLinkDirEntry(p) {
  if (!isDirectChild(p, linkDir)) throw new Error(`Refusing to touch ${p}: not an entry of ${linkDir}`)
}

function removeLink(p) {
  assertLinkDirEntry(p)
  if (!lstatOrNull(p)?.isSymbolicLink()) throw new Error(`Refusing to unlink ${p}: not a link`)
  fs.unlinkSync(p)
}

function createLink(name, target) {
  const finalPath = path.join(linkDir, name)
  const tempPath = path.join(linkDir, `${TEMP_PREFIX}${process.pid}-${name}`)
  assertLinkDirEntry(finalPath)
  assertLinkDirEntry(tempPath)
  fs.symlinkSync(target, tempPath, 'junction')
  try {
    fs.renameSync(tempPath, finalPath)
  } catch (e) {
    removeLink(tempPath)
    // Another session may have linked it first, which is the same end state.
    if (!isValidLink(finalPath, target)) throw e
  }
}

function linkTarget(p) {
  return path.resolve(path.dirname(p), fs.readlinkSync(p))
}

function isValidLink(p, target) {
  return Boolean(lstatOrNull(p)?.isSymbolicLink()) && samePath(linkTarget(p), target)
}

function pidIsAlive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch (e) {
    return e.code === 'EPERM'
  }
}

// Leftovers of a run that was killed. A live pid means another sync is mid-flight.
function clearTempEntry(name) {
  const p = path.join(linkDir, name)
  const pid = Number(name.slice(TEMP_PREFIX.length).split('-')[0])
  if (Number.isInteger(pid) && pid > 0 && pidIsAlive(pid)) return
  if (checkOnly) {
    problems.push(`leftover temporary entry ${name}`)
    return
  }
  assertLinkDirEntry(p)
  const stat = lstatOrNull(p)
  if (!stat) return
  if (stat.isSymbolicLink()) {
    fs.unlinkSync(p)
  } else if (stat.isDirectory()) {
    // A junction interrupted mid-creation is an empty directory. rmdir is not
    // recursive, so a directory with anything inside it stays.
    try {
      fs.rmdirSync(p)
    } catch {
      problems.push(`temporary entry ${name} is not empty, left in place`)
      return
    }
  } else {
    problems.push(`temporary entry ${name} is a file, left in place`)
    return
  }
  removed.push(name)
}

function wantedSkills() {
  let lock
  try {
    lock = JSON.parse(fs.readFileSync(path.join(root, 'skills-lock.json'), 'utf8'))
  } catch (e) {
    fail(`Cannot read skills-lock.json: ${e.message}`)
  }
  const wanted = new Map()
  for (const [name, entry] of Object.entries(lock.skills ?? {})) {
    if (PLUGIN_SOURCES.has(entry.source)) continue
    if (!SAFE_NAME.test(name) || RESERVED_NAMES.has(name)) {
      problems.push(`skipped ${JSON.stringify(name)}: unsafe skill name`)
      continue
    }
    const target = path.join(canonicalDir, name)
    const stat = lstatOrNull(target)
    if (!stat?.isDirectory() || stat.isSymbolicLink()) {
      problems.push(`skipped ${name}: ${target} is not a real directory`)
      continue
    }
    // The skill must really live in the library, not just appear to.
    if (!isDirectChild(fs.realpathSync(target), fs.realpathSync(canonicalDir))) {
      problems.push(`skipped ${name}: resolves outside .agents/skills/`)
      continue
    }
    if (!lstatOrNull(path.join(target, 'SKILL.md'))?.isFile()) {
      problems.push(`skipped ${name}: no SKILL.md`)
      continue
    }
    wanted.set(name, target)
  }
  return wanted
}

function reconcileExisting(wanted) {
  for (const name of fs.readdirSync(linkDir)) {
    if (name.startsWith(TEMP_PREFIX)) {
      clearTempEntry(name)
      continue
    }
    const p = path.join(linkDir, name)
    const stat = lstatOrNull(p)
    if (!stat?.isSymbolicLink()) {
      // Real files and folders aren't ours, such as a recipe /verify recorded.
      if (wanted.has(name)) problems.push(`${name} is a real folder, not a link; left in place`)
      continue
    }
    const target = linkTarget(p)
    if (wanted.has(name) && samePath(target, wanted.get(name))) continue
    if (!isDirectChild(target, canonicalDir)) {
      problems.push(`${name} points outside .agents/skills/ (${target}); left in place`)
      continue
    }
    // Ours but stale: the skill left the lock file or the link has the wrong target.
    if (checkOnly) {
      problems.push(`stale link ${name}`)
      continue
    }
    removeLink(p)
    removed.push(name)
  }
}

function createMissing(wanted) {
  for (const [name, target] of wanted) {
    if (lstatOrNull(path.join(linkDir, name))) continue
    if (checkOnly) {
      problems.push(`missing link ${name}`)
      continue
    }
    createLink(name, target)
    created.push(name)
  }
}

function verify(wanted) {
  const canonicalReal = fs.realpathSync(canonicalDir)
  for (const [name, target] of wanted) {
    const p = path.join(linkDir, name)
    if (!lstatOrNull(p)?.isSymbolicLink()) continue
    if (!isValidLink(p, target) || !isDirectChild(fs.realpathSync(p), canonicalReal)) {
      problems.push(`${name} did not verify after sync`)
    }
  }
}

function main() {
  if (!lstatOrNull(canonicalDir)?.isDirectory() || lstatOrNull(canonicalDir).isSymbolicLink()) {
    fail(`${canonicalDir} must be a real directory.`)
  }
  const existing = lstatOrNull(linkDir)
  // If .claude/skills were itself a link, removing "links" in it could reach the library.
  if (existing?.isSymbolicLink()) fail(`${linkDir} is a link. Remove it by hand, then run this again.`)
  if (existing && !existing.isDirectory()) fail(`${linkDir} is not a directory.`)
  if (!existing) {
    if (checkOnly) fail(`${linkDir} does not exist. Run this script without --check.`)
    fs.mkdirSync(linkDir)
  }

  const wanted = wantedSkills()
  reconcileExisting(wanted)
  createMissing(wanted)
  verify(wanted)

  if (created.length || removed.length) {
    console.log(`[sync-skills] linked ${created.length}, removed ${removed.length}. ${wanted.size} skills expected. New links load in the next session.`)
  }
  for (const problem of problems) console.log(`[sync-skills] ${problem}`)
  process.exit(problems.length ? 1 : 0)
}

main()
