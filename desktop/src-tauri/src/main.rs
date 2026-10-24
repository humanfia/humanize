// No console beside the window on Windows, but while it is developed.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    humanize_lib::run();
}
