//! The broker: where two halves meet when neither can dial the other. Port of
//! `hmz.coganchor.rendezvous` and `hmz internal anchor rendezvous`. [Unit 3]
//!
//! A ticket names a meeting. Each half dials the broker with it and says which half it is;
//! the broker tells each what the other looks like from outside, starts them at each other at
//! the same instant (hole punching), and carries the bytes itself where they cannot meet.

pub mod peer;
pub mod server;

use std::fmt;

pub use peer::dial;
pub use server::Broker;

use crate::cli::BrokerArgs;

/// Which half of a session is dialling.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    /// The cog's side, spelled `"anchor"` on the wire as the Python half named it.
    Anchor,
    /// The anchor's side, spelled `"serve"` on the wire.
    Serve,
}

impl Role {
    /// The role as the broker's line protocol spells it.
    pub fn as_str(self) -> &'static str {
        match self {
            Role::Anchor => "anchor",
            Role::Serve => "serve",
        }
    }
}

/// A meeting at a broker: `TICKET@HOST:PORT`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Meeting {
    pub ticket: String,
    pub host: String,
    pub port: u16,
}

impl Meeting {
    /// Reads `TICKET@HOST:PORT` (split at the first `@`, then the last `:`, `[]` stripped).
    pub fn parse(said: &str) -> Result<Meeting, String> {
        todo!("unit 3")
    }

    /// A new, unguessable ticket at this broker: 32 hex digits.
    pub fn fresh(host: &str, port: u16) -> Meeting {
        todo!("unit 3")
    }
}

impl fmt::Display for Meeting {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}@{}:{}", self.ticket, self.host, self.port)
    }
}

/// `coganchor broker`: listen, say so, and hold meetings until interrupted.
pub fn main(args: BrokerArgs) -> i32 {
    server::main(args)
}
