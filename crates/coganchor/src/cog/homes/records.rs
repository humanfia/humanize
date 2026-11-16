//! The paths of a virtual home a CLI's databases hold, said again with its links followed as
//! it is dropped. Port of `hmz.coganchor.homes._respelled`.

use std::path::Path;
use std::time::Duration;

use rusqlite::{Connection, params};

use super::paths::{fnmatch, glob, realpath};

/// Says each path under `at` that a CLI's databases hold with the home's links followed.
///
/// Only through a database that is a link, which is the user's, or one of the home's own that
/// is moved out of it as it is dropped (`moved`, globs of its names): any other goes with it.
/// And only one the agent may write (`writable`) where its links lead. A path whose file is
/// not there to follow to is left as it was. Never fails: what cannot be read is logged.
pub fn respelled(
    at: &Path,
    records: &[(String, String, String)],
    moved: &[String],
    writable: &dyn Fn(&str) -> bool,
) {
    let root = format!("{}/", at.display());
    for (pattern, table, column) in records {
        for database in glob(at, pattern) {
            let linked =
                std::fs::symlink_metadata(&database).is_ok_and(|one| one.file_type().is_symlink());
            let name = database
                .file_name()
                .map(|one| one.to_string_lossy().into_owned())
                .unwrap_or_default();
            if !linked && !moved.iter().any(|one| fnmatch(&name, one)) {
                continue;
            }
            if !writable(&realpath(&database).to_string_lossy()) {
                tracing::warn!(
                    "not respelling {}: the agent may not write it",
                    database.display()
                );
                continue;
            }
            let connection = match Connection::open(&database) {
                Ok(one) => one,
                Err(why) => {
                    tracing::warn!("could not read {}: {why}", database.display());
                    continue;
                }
            };
            if let Err(why) = respell(&connection, &root, table, column) {
                tracing::warn!(
                    "could not respell {column} in {}: {why}",
                    database.display()
                );
            }
        }
    }
}

/// One table's column of one database: each row naming a path under `root` whose links lead
/// to a file that is there is said again as where they lead, in one transaction.
fn respell(connection: &Connection, root: &str, table: &str, column: &str) -> rusqlite::Result<()> {
    connection.busy_timeout(Duration::from_secs(10))?;
    // Names of ours, quoted as Python quotes them.
    let mut select = connection.prepare(&format!(
        "select rowid, \"{column}\" from \"{table}\" where substr(\"{column}\", 1, ?) = ?"
    ))?;
    let rows: Vec<(i64, Option<String>)> = select
        .query_map(params![root.chars().count() as i64, root], |row| {
            Ok((row.get(0)?, row.get::<_, String>(1).ok()))
        })?
        .collect::<Result<_, _>>()?;
    let mut changes = Vec::new();
    for (row, path) in rows {
        let Some(path) = path else { continue };
        let followed = realpath(Path::new(&path));
        let there = followed.exists();
        let followed = followed.to_string_lossy().into_owned();
        if followed != path && there {
            changes.push((followed, row));
        }
    }
    if changes.is_empty() {
        return Ok(());
    }
    let transaction = connection.unchecked_transaction()?;
    for (followed, row) in changes {
        transaction.execute(
            &format!("update \"{table}\" set \"{column}\" = ? where rowid = ?"),
            params![followed, row],
        )?;
    }
    transaction.commit()
}
