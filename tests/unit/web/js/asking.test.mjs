import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  blockSummary,
  chartRows,
  diffStats,
  fieldsOf,
  imageSource,
  isLong,
  keepDraft,
  secretOf,
  kindOf,
  labelOf,
  paramLabel,
  multiline,
  opened,
  patchFiles,
  problems,
  pruneDrafts,
  readDraft,
  refusalErrors,
  requiredLeft,
  resolved,
  sendLabel,
  summaryOf,
  untouched,
  draftable,
  widgetOf,
  withdrawnWhy,
  yesNo,
} from '../../../../src/hmz/web/static/asking/logic.js'

/** A schema as pydantic writes one for a review: a choice, notes, a nested model and a list. */
const REVIEW = {
  title: 'Review',
  type: 'object',
  $defs: {
    Verdict: { enum: ['approve', 'request changes', 'reject'], title: 'Verdict', type: 'string' },
    Scope: { properties: { files: { type: 'integer', minimum: 1 }, owner: { type: 'string' } }, required: ['files'], title: 'Scope', type: 'object' },
  },
  properties: {
    tests: { default: true, description: 'Write tests', title: 'Tests', type: 'boolean' },
    verdict: { $ref: '#/$defs/Verdict' },
    notes: { title: 'Notes', type: 'string', maxLength: 500 },
    reviewer: { anyOf: [{ type: 'string', format: 'email' }, { type: 'null' }], default: null, title: 'Reviewer' },
    scope: { $ref: '#/$defs/Scope' },
    tags: { items: { type: 'string' }, title: 'Tags', type: 'array', default: [] },
  },
  required: ['verdict', 'notes', 'scope'],
}

test('a $ref is followed, an optional is its type let go of null, and a union of constants is a choice', () => {
  assert.deepEqual(resolved(REVIEW.properties.verdict, REVIEW).node.enum, ['approve', 'request changes', 'reject'])
  const reviewer = resolved(REVIEW.properties.reviewer, REVIEW)
  assert.equal(reviewer.nullable, true)
  assert.equal(reviewer.node.format, 'email')
  assert.deepEqual(resolved({ anyOf: [{ const: 'a' }, { const: 'b' }] }).node.enum, ['a', 'b'])
  assert.equal(resolved({ allOf: [{ $ref: '#/$defs/Scope' }], description: 'how wide' }, REVIEW).node.description, 'how wide')
  assert.equal(resolved({ type: ['integer', 'null'] }).node.type, 'integer')
})

test('each type is asked as its own kind of field, and a widget hint is read', () => {
  assert.equal(kindOf({ enum: [1, 2] }), 'choice')
  assert.equal(kindOf({ const: 'x' }), 'choice')
  assert.equal(kindOf({ type: 'boolean' }), 'boolean')
  assert.equal(kindOf({ type: 'integer' }), 'integer')
  assert.equal(kindOf({ type: 'object', properties: {} }), 'object')
  assert.equal(kindOf({ type: 'array', items: { type: 'string' } }), 'array')
  assert.equal(kindOf({ type: 'object', additionalProperties: true }), 'json')
  assert.equal(kindOf({}), 'json')
  assert.equal(widgetOf({ type: 'string', 'hmz:widget': 'markdown' }), 'markdown')
  assert.equal(widgetOf({ type: 'string', 'hmz:widget': 'html' }), '')
})

test('fields are read required first, then optional, then suggested, each in the order written', () => {
  const fields = fieldsOf(REVIEW)
  assert.deepEqual(
    fields.map((one) => one.name),
    ['verdict', 'notes', 'scope', 'tests', 'reviewer', 'tags'],
  )
  const tests = fields.find((one) => one.name === 'tests')
  assert.equal(tests.suggested, true)
  assert.equal(tests.value, true)
  assert.equal(tests.folded, true)
  assert.equal(fields[0].required, true)
})

test('a field is named in a sentence, its title kept only where it says more than its name', () => {
  assert.equal(labelOf('dry_run', { title: 'Dry Run' }), 'Dry run')
  assert.equal(labelOf('max_files', { title: 'How many files at most' }), 'How many files at most')
  assert.equal(labelOf('reviewerEmail'), 'Reviewer email')
})

test("a flow's param is named by the title the flow gave it, else by its key as -p takes it", () => {
  const fields = fieldsOf({
    type: 'object',
    properties: { first_chaser_cost: { type: 'number', default: 1 }, passes: { type: 'integer', title: 'Review passes', default: 1 }, dryRun: { type: 'boolean', default: false } },
  })
  assert.deepEqual(
    fields.map((one) => paramLabel(one.name, one.node)),
    ['first_chaser_cost', 'Review passes', 'dryRun'],
  )
})

test('a field is named by its own title, never by the title of the type it refers to', () => {
  const schema = {
    type: 'object',
    properties: {
      severity: { $ref: '#/$defs/Level' },
      confidence: { $ref: '#/$defs/Level' },
      actor_limits: { $ref: '#/$defs/Limits' },
      reviewer_limits: { anyOf: [{ $ref: '#/$defs/Limits' }, { type: 'null' }], default: null },
      shade: { $ref: '#/$defs/Level', title: 'Which shade' },
    },
    required: ['severity', 'confidence', 'actor_limits', 'shade'],
    $defs: {
      Level: { title: 'Level', type: 'string', enum: ['low', 'high'] },
      Limits: { title: 'Limits', type: 'object', properties: { turns: { title: 'Turns', type: 'integer' } } },
    },
  }
  const fields = fieldsOf(schema)
  assert.deepEqual(
    fields.map((one) => labelOf(one.name, one.node)),
    ['Severity', 'Confidence', 'Actor limits', 'Which shade', 'Reviewer limits'],
  )
  assert.deepEqual(fields.map((one) => kindOf(one.node)), ['choice', 'choice', 'object', 'choice', 'object'])
})

test('a yes or no is worded from what it is about', () => {
  assert.deepEqual(yesNo('tests', { description: 'Write tests.' }), { yes: 'Yes, write tests', no: 'No' })
  assert.deepEqual(yesNo('dry_run', { title: 'Dry Run' }), { yes: 'Yes, dry run', no: 'No' })
  assert.deepEqual(yesNo('rewrite', { description: 'Whether the agent should go on and rewrite every file it touched since it began' }), { yes: 'Yes, rewrite', no: 'No' })
})

test('text likely to run long is asked on several lines', () => {
  assert.equal(multiline('notes', { type: 'string' }), true)
  assert.equal(multiline('name', { type: 'string' }), false)
  assert.equal(multiline('name', { type: 'string', maxLength: 2000 }), true)
  assert.equal(multiline('snippet', { type: 'string', 'hmz:widget': 'code' }), true)
})

test('what does not fit is said in plain words, at the path of the field it is of', () => {
  const found = problems(REVIEW, { verdict: 'maybe', notes: '', scope: { files: 0 }, reviewer: 'nobody', tags: ['a', 3] })
  const at = Object.fromEntries(found.map((one) => [one.path.join('/'), one.message]))
  assert.match(at.verdict, /^Pick one of “approve”, “request changes”, “reject”\.$/)
  assert.equal(at.notes, 'This needs an answer.')
  assert.equal(at['scope/files'], 'At least 1.')
  assert.match(at.reviewer, /email address/)
  assert.equal(at['tags/1'], 'This needs text.')
  assert.deepEqual(problems(REVIEW, { verdict: 'approve', notes: 'LGTM', scope: { files: 2 }, reviewer: null }), [])
  assert.deepEqual(problems(REVIEW, { verdict: 'approve', notes: 'x'.repeat(501), scope: { files: 2 } })[0], { path: ['notes'], message: 'At most 500 characters (501 now).' })
  assert.deepEqual(problems({ type: 'integer' }, 1.5), [{ path: [], message: 'This needs a whole number.' }])
  assert.deepEqual(problems({ type: 'array', items: { type: 'string' }, minItems: 2 }, ['a']), [{ path: [], message: 'At least 2 items.' }])
})

test('what is left to say counts each required field still blank, nested ones too', () => {
  assert.equal(requiredLeft(REVIEW, {}), 3)
  assert.equal(requiredLeft(REVIEW, { verdict: 'approve' }), 2)
  assert.equal(requiredLeft(REVIEW, { verdict: 'approve', notes: 'ok', scope: {} }), 1)
  assert.equal(requiredLeft(REVIEW, { verdict: 'approve', notes: 'ok', scope: { files: 3 } }), 0)
  assert.equal(sendLabel(2), '2 required left')
  assert.equal(sendLabel(0), 'Send answer')
})

test('an optional object is untouched while each field is blank, off, or still its suggestion', () => {
  const inner = { type: 'object', properties: { label: { type: 'string' }, depth: { type: 'integer', default: 1 }, deep: { type: 'boolean', default: true } }, required: ['label'] }
  const fields = fieldsOf(inner)
  // What a form reads of it before anybody types: the suggestions it filled in, the rest blank.
  assert.equal(untouched(fields, { label: '', depth: 1, deep: true }), true)
  assert.equal(untouched(fields, { depth: 1, deep: false }), true)
  assert.equal(untouched(fields, { label: '', depth: 2, deep: true }), false)
  assert.equal(untouched(fields, { label: 'L', depth: 1, deep: true }), false)
  // A number nobody suggested is somebody's answer.
  assert.equal(untouched(fieldsOf({ type: 'object', properties: { depth: { type: 'integer' } } }), { depth: 1 }), false)
  // An object it must hold, itself as first shown, does not make it touched.
  const outer = { type: 'object', properties: { mid: { $ref: '#/$defs/Inner' } }, required: ['mid'], $defs: { Inner: inner } }
  assert.equal(untouched(fieldsOf(outer, outer), { mid: { label: '', depth: 1, deep: true } }, outer), true)
  assert.equal(untouched(fieldsOf(outer, outer), { mid: { label: 'L', depth: 1, deep: true } }, outer), false)
})

test('an answer is said back in one line, choices plain and text quoted', () => {
  assert.equal(summaryOf({ verdict: 'approve', notes: 'LGTM', tests: false }, REVIEW), 'approve · ‘LGTM’ · tests: no')
  assert.equal(summaryOf('yes'), '‘yes’')
  assert.equal(summaryOf({ tags: ['a', 'b'] }), 'a, b')
  assert.equal(summaryOf({}), '(nothing)')
  assert.ok(summaryOf({ notes: 'x'.repeat(300) }, REVIEW).length <= 90)
})

test('a question withdrawn says why', () => {
  assert.equal(withdrawnWhy('away', 'reviewer'), 'reviewer went away')
  assert.equal(withdrawnWhy('over'), 'the run ended')
  assert.equal(withdrawnWhy(''), 'it is no longer asked')
})

const PATCH = `diff --git a/src/a.py b/src/a.py
index 1..2 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,3 @@
 keep
-old
+new
+more
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-was
+is
`

test('a diff is read a file at a time, and summed up as what it adds and removes', () => {
  const files = patchFiles(PATCH)
  assert.deepEqual(
    files.map((one) => [one.name, one.added, one.removed]),
    [
      ['src/a.py', 2, 1],
      ['README.md', 1, 1],
    ],
  )
  assert.deepEqual(diffStats(PATCH), { added: 3, removed: 2, files: 2 })
  assert.equal(blockSummary({ kind: 'diff', patch: PATCH }), '+3 −2 in 2 files')
  // A patch of several files without `diff --git` names each by its `---`.
  assert.equal(patchFiles('--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-c\n+d\n').length, 2)
})

test('each block is summed up in a line, and folded where it is long, the first always open', () => {
  assert.equal(blockSummary({ kind: 'table', columns: ['a'], rows: [[1], [2]] }), 'table · 2 rows')
  assert.equal(blockSummary({ kind: 'code', text: 'a\nb', language: 'py' }), 'py · 2 lines')
  assert.equal(blockSummary({ kind: 'json', value: { a: 1 } }), 'json · 1 key')
  assert.equal(blockSummary({ kind: 'image', alt: 'plot' }), 'image · plot')
  assert.equal(blockSummary({ kind: 'chart', spec: { mark: 'bar', data: { values: [{ a: 1 }] } } }), 'chart · bar · 1 point')
  const rows = Array.from({ length: 40 }, (_, n) => [n])
  assert.equal(isLong({ kind: 'table', columns: ['n'], rows }), true)
  assert.deepEqual(opened([{ kind: 'table', columns: ['n'], rows }, { kind: 'markdown', text: 'short' }, { kind: 'table', columns: ['n'], rows }]), [true, true, false])
})

test('a chart falls back to the table of what it is drawn from', () => {
  assert.deepEqual(chartRows({ data: { values: [{ x: 1, y: 2 }, { x: 2, z: 3 }] } }), {
    columns: ['x', 'y', 'z'],
    rows: [
      [1, 2, undefined],
      [2, undefined, 3],
    ],
  })
  assert.deepEqual(chartRows({}), { columns: [], rows: [] })
})

test('an image is shown only as an image', () => {
  assert.equal(imageSource({ mime: 'image/png', data: 'AAA=' }), 'data:image/png;base64,AAA=')
  assert.equal(imageSource({ mime: 'text/html', data: 'AAA=' }), '')
})

/** A storage held in memory, as localStorage keeps strings. */
function storage() {
  const kept = new Map()
  return {
    get length() {
      return kept.size
    },
    key: (n) => [...kept.keys()][n] ?? null,
    getItem: (key) => kept.get(key) ?? null,
    setItem: (key, value) => kept.set(key, String(value)),
    removeItem: (key) => kept.delete(key),
  }
}

test('a draft is kept per question, read back, forgotten once answered, and pruned once old', () => {
  const kept = storage()
  keepDraft('q1', { notes: 'half' }, kept)
  assert.deepEqual(readDraft('q1', kept), { notes: 'half' })
  assert.equal(readDraft('q2', kept), undefined)
  keepDraft('q1', undefined, kept)
  assert.equal(readDraft('q1', kept), undefined)
  keepDraft('old', 'x', kept)
  pruneDrafts(14, kept, Date.now() + 15 * 86400000)
  assert.equal(readDraft('old', kept), undefined)
  // A browser that keeps nothing forgets, and the form works the same.
  const refusing = { getItem: () => { throw new Error('no') }, setItem: () => { throw new Error('no') } }
  assert.equal(readDraft('q', refusing), undefined)
  keepDraft('q', 1, refusing)
})

test('a refusal of an answer is read for the errors of each field', () => {
  const refused = Object.assign(new Error('the answer does not fit: verdict'), { code: 400, data: { errors: [{ path: ['verdict'], message: 'Input should be approve' }, { nope: 1 }] } })
  assert.deepEqual(refusalErrors(refused), [{ path: ['verdict'], message: 'Input should be approve' }])
  assert.deepEqual(refusalErrors(Object.assign(new Error('x'), { said: { errors: [{ path: [], message: 'no' }] } })), [{ path: [], message: 'no' }])
  assert.deepEqual(refusalErrors(new Error('gone')), [])
})

test('a secret is never kept in a draft and is said back as stars', () => {
  const schema = { type: 'object', properties: { user: { type: 'string' }, token: { type: 'string', 'hmz:widget': 'secret' }, pin: { type: 'string', format: 'password' } } }
  assert.ok(secretOf(schema.properties.token))
  assert.deepEqual(draftable({ user: 'ann', token: 's3cret', pin: '1234' }, schema), { user: 'ann' })
  assert.equal(summaryOf({ user: 'ann', token: 's3cret' }, schema), '‘ann’ · token: ***')
})
