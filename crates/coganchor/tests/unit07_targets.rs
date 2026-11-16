//! Target spellings, read as Python's `hmz.coganchor.transport` reads them.
//!
//! `unit07_targets.json` is what `unit07_targets.py` had Python make of each of a hundred
//! spellings: the spelling back, the fields, the road's line, cache and mirrors, or the
//! refusal. The port has to make the same of every one.

use std::ffi::OsString;

use coganchor::transport::{Road, Target};
use serde_json::Value;

#[test]
fn targets_read_as_python_reads_them() {
    // As the fixture was made: no connection reuse, whose control path is this machine's.
    // The only test in this binary, so nothing else reads the environment meanwhile.
    unsafe { std::env::set_var("HUMANIZE_SSH_REUSE", "off") };
    let table: Vec<Value> =
        serde_json::from_str(include_str!("unit07_targets.json")).expect("the fixture");
    assert!(table.len() > 90);
    let mut wrong = Vec::new();
    for case in &table {
        let said = case["said"].as_str().unwrap();
        let parsed = Target::parse(said);
        if let Some(error) = case.get("error") {
            match parsed {
                Err(ours) if ours == error.as_str().unwrap() => {}
                other => wrong.push(format!(
                    "{said:?}: Python refused with {error}, Rust {other:?}"
                )),
            }
            continue;
        }
        let target = match parsed {
            Ok(target) => target,
            Err(error) => {
                wrong.push(format!("{said:?}: Rust refused it: {error}"));
                continue;
            }
        };
        check(&mut wrong, case, "describe", Value::from(target.describe()));
        check(
            &mut wrong,
            case,
            "scheme",
            Value::from(target.scheme.clone()),
        );
        // Python keeps an ssh target's user in its host.
        let host = if target.scheme == "ssh" {
            target.login()
        } else {
            target.host.clone()
        };
        check(&mut wrong, case, "host", Value::from(host));
        check(
            &mut wrong,
            case,
            "port",
            Value::from(target.port.unwrap_or(0)),
        );
        check(
            &mut wrong,
            case,
            "path",
            Value::from(target.path.clone().unwrap_or_default()),
        );
        check(
            &mut wrong,
            case,
            "options",
            serde_json::to_value(
                target
                    .options
                    .iter()
                    .map(|(key, value)| [key, value])
                    .collect::<Vec<_>>(),
            )
            .unwrap(),
        );
        // What it spells back reads as the same target again.
        if Target::parse(&target.describe()).as_ref() != Ok(&target) {
            wrong.push(format!(
                "{said:?}: {} does not read back",
                target.describe()
            ));
        }
        if case.get("cache").is_none() {
            continue;
        }
        let road = Road::to(&target);
        check(&mut wrong, case, "cache", Value::from(road.cache()));
        check(&mut wrong, case, "mirrors", Value::from(road.mirrors()));
        check(&mut wrong, case, "owned", Value::from(road.owned()));
        if case.get("line").is_some() {
            let argv: Vec<OsString> = ["prog", "a b", "it's"].map(OsString::from).to_vec();
            let line: Vec<String> = road
                .try_line(&argv)
                .unwrap()
                .into_iter()
                .map(|word| word.into_string().unwrap())
                .collect();
            check(
                &mut wrong,
                case,
                "line",
                serde_json::to_value(line).unwrap(),
            );
        }
    }
    assert!(
        wrong.is_empty(),
        "{} differences:\n{}",
        wrong.len(),
        wrong.join("\n")
    );
}

/// Notes in `wrong` where `ours` is not what Python said of `what`.
fn check(wrong: &mut Vec<String>, case: &Value, what: &str, ours: Value) {
    if ours != case[what] {
        let said = &case["said"];
        wrong.push(format!(
            "{said}: {what} is {ours}, Python says {}",
            case[what]
        ));
    }
}
