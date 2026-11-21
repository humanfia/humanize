// The writes of protocol/openrpc.json (Section 6.2.3 of protocol/wire.md): the methods whose
// parameters include `idem`. tests/unit/web/js checks this list against that document.

/** Every write, by its method. */
export const WRITES = new Set([
  'pair.create', 'devices.revoke', 'hosts.stop', 'epic.start', 'epic.say', 'epic.answer',
  'epic.stop', 'epic.force', 'epic.afk', 'epic.claim', 'epic.release', 'epic.board', 'epic.quit',
  'runs.backup', 'runs.import', 'backups.pull', 'flows.setup', 'flows.fork', 'workspaces.add',
  'workspaces.forget', 'flowverses.add', 'flowverses.fetch', 'flowverses.remove',
  'flowverses.install', 'flowverses.uninstall', 'settings.set', 'settings.forget',
  'accounts.create', 'accounts.correct', 'accounts.remove', 'accounts.models', 'accounts.copy',
  'nous.scan', 'nous.set', 'nous.rename', 'nous.clear', 'runtimes.set', 'runtimes.remove', 'runtimes.import',
  'easytier.set', 'easytier.remove', 'aichan.create', 'aichan.rename', 'aichan.forget', 'hosts.env.write',
  'hosts.env.exec', 'env.write', 'env.mkdir', 'env.rename', 'env.remove', 'env.git.stage',
  'env.git.unstage', 'env.git.discard', 'env.git.commit', 'env.git.rewind',
  'chat.start', 'chat.say', 'chat.set', 'chat.move', 'chat.stop', 'chat.rename', 'chat.agent', 'chat.fork', 'chat.archive',
  'chat.unarchive', 'chat.backup', 'chat.delete',
  'chat.harness.adopt',
])
