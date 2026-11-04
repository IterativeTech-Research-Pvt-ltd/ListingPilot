#!/usr/bin/env node
// PreToolUse hook for shell tools. The rules live in guard-rules.mjs.
//
// This entry always runs them, and any crash exits non-zero. settings.json sets
// onFailure to "block", so a broken guard stops the command instead of waving it
// through.

import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { decide } from './guard-rules.mjs'

const CLAIM_DIR = path.join(os.tmpdir(), 'listingpilot-pytest-claim')
const CLAIM_MS = 5000

function isPytestRunning() {
  const result = process.platform === 'win32'
    ? spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name = 'pytest.exe'\" | ForEach-Object { $_.CommandLine }"], { encoding: 'utf8', timeout: 8000 })
    : spawnSync('ps', ['-eo', 'args'], { encoding: 'utf8', timeout: 8000 })
  if (result.error || result.status !== 0) return null
  return /(^|[\s\\/"])py\.?test(\.exe)?(["\s]|$)/m.test(result.stdout)
}

// mkdir is atomic, so of two commands started together only one gets through.
// The claim only has to last until the pytest process is visible.
function claimPytest() {
  try {
    fs.mkdirSync(CLAIM_DIR)
    return true
  } catch (e) {
    if (e.code !== 'EEXIST') throw e
  }
  if (Date.now() - fs.statSync(CLAIM_DIR).mtimeMs < CLAIM_MS) return false
  fs.rmdirSync(CLAIM_DIR)
  try {
    fs.mkdirSync(CLAIM_DIR)
    return true
  } catch {
    return false
  }
}

const input = JSON.parse(fs.readFileSync(0, 'utf8').replace(/^﻿/, ''))
const command = input.tool_input?.command
if (typeof command === 'string' && command.trim()) {
  const { decision, reason } = decide(command, { agentType: input.agent_type, isPytestRunning, claimPytest })
  if (decision !== 'allow') {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: decision, permissionDecisionReason: `[ListingPilot guard] ${reason}` },
    }))
  }
}
