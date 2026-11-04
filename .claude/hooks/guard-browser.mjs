#!/usr/bin/env node
// PreToolUse hook for Claude in Chrome tools. The rules live in guard-rules.mjs.
// As with guard-bash.mjs, a crash exits non-zero and settings.json blocks the call.

import fs from 'node:fs'

import { decideBrowser } from './guard-rules.mjs'

const input = JSON.parse(fs.readFileSync(0, 'utf8').replace(/^﻿/, ''))
const { decision, reason } = decideBrowser(input.tool_name ?? '', input.tool_input, input.agent_type)
if (decision !== 'allow') {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: decision, permissionDecisionReason: `[ListingPilot guard] ${reason}` },
  }))
}
