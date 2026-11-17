//! Logging to standard error, in the shape `hmz` logs: `<time> hmz <LEVEL> <message>`.
//!
//! The level is `--log-level` where given, else `HUMANIZE_LOG`, else the command's default.
//! A `HUMANIZE_LOG` that names no level is reported once and ignored.

use std::io::Write;

use tracing::Level;

/// The levels `--log-level` and `HUMANIZE_LOG` accept.
pub const LEVELS: [&str; 4] = ["debug", "info", "warning", "error"];

/// The level a spelling names, if it is one of [`LEVELS`].
pub fn level(said: &str) -> Option<Level> {
    Some(match said {
        "debug" => Level::DEBUG,
        "info" => Level::INFO,
        "warning" => Level::WARN,
        "error" => Level::ERROR,
        _ => return None,
    })
}

/// Settles the level from the option, the environment and the default, and installs the
/// logger. Says so on standard error when `HUMANIZE_LOG` names no level.
pub fn init(option: Option<&str>, default: &str) {
    let chosen = match option {
        Some(said) => said.to_owned(),
        None => match std::env::var("HUMANIZE_LOG") {
            Ok(raw) => {
                let said = raw.trim().to_lowercase();
                if level(&said).is_some() {
                    said
                } else {
                    if !raw.trim().is_empty() {
                        eprintln!(
                            "hmz: ignoring HUMANIZE_LOG='{raw}', which is not one of {}",
                            LEVELS.join(", ")
                        );
                    }
                    default.to_owned()
                }
            }
            Err(_) => default.to_owned(),
        },
    };
    let max = level(&chosen).unwrap_or(Level::WARN);
    let _ = tracing_subscriber::fmt()
        .with_max_level(max)
        .with_writer(std::io::stderr)
        .event_format(Format)
        .try_init();
}

struct Format;

impl<S, N> tracing_subscriber::fmt::FormatEvent<S, N> for Format
where
    S: tracing::Subscriber + for<'a> tracing_subscriber::registry::LookupSpan<'a>,
    N: for<'a> tracing_subscriber::fmt::FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        ctx: &tracing_subscriber::fmt::FmtContext<'_, S, N>,
        mut writer: tracing_subscriber::fmt::format::Writer<'_>,
        event: &tracing::Event<'_>,
    ) -> std::fmt::Result {
        let now =
            time::OffsetDateTime::now_local().unwrap_or_else(|_| time::OffsetDateTime::now_utc());
        let stamp = now
            .format(time::macros::format_description!(
                "[year]-[month]-[day] [hour]:[minute]:[second],[subsecond digits:3]"
            ))
            .unwrap_or_default();
        let name = match *event.metadata().level() {
            Level::ERROR => "ERROR",
            Level::WARN => "WARNING",
            Level::INFO => "INFO",
            _ => "DEBUG",
        };
        write!(writer, "{stamp} hmz {name} ")?;
        ctx.field_format().format_fields(writer.by_ref(), event)?;
        writeln!(writer)
    }
}

/// Writes `hmz: <message>` to standard error, flushed.
pub fn say(message: impl std::fmt::Display) {
    let mut err = std::io::stderr().lock();
    let _ = writeln!(err, "hmz: {message}");
    let _ = err.flush();
}
