//! The Rust router answers every case of `fixtures/unit08_router.json` as Python's `Router`
//! did when `fixtures/unit08_router.py` wrote it.

use coganchor::cog::router::{Layout, Router, RouterConfig};
use serde_json::Value;

fn strings(value: &Value) -> Vec<String> {
    value
        .as_array()
        .map(|all| {
            all.iter()
                .map(|one| one.as_str().unwrap().to_owned())
                .collect()
        })
        .unwrap_or_default()
}

fn pairs(value: &Value) -> Vec<(String, String)> {
    value
        .as_array()
        .map(|all| {
            all.iter()
                .map(|one| {
                    (
                        one[0].as_str().unwrap().to_owned(),
                        one[1].as_str().unwrap().to_owned(),
                    )
                })
                .collect()
        })
        .unwrap_or_default()
}

fn build(config: &Value, platform: &str) -> Router {
    let layouts = config["layouts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|one| Layout::create(one[0].as_str().unwrap(), one[1].as_str()))
        .collect();
    let router = Router::new(RouterConfig {
        layouts,
        aliases: pairs(&config["aliases"]),
        local_paths: strings(&config["local_paths"]),
        local_programs: strings(&config["local_programs"]),
        redirects: pairs(&config["redirects"]),
    });
    router.learn_platform(platform);
    router
}

#[test]
fn every_case_is_answered_as_python_answered_it() {
    let text = include_str!("fixtures/unit08_router.json");
    let cases: Vec<Value> = serde_json::from_str(text).unwrap();
    let mut checked = 0;
    for case in &cases {
        let platform = case["platform"].as_str().unwrap();
        let router = build(&case["config"], platform);
        let at = format!("{} on {platform:?}", case["config"]);
        assert_eq!(router.settles(), case["settles"].as_bool().unwrap(), "{at}");
        for (path, said) in case["paths"].as_object().unwrap() {
            assert_eq!(
                router.canonical(path),
                said["canonical"].as_str().unwrap(),
                "canonical {path} under {at}"
            );
            assert_eq!(
                router.to_virtual(path).as_deref(),
                said["virtual"].as_str(),
                "virtual {path} under {at}"
            );
            assert_eq!(
                router.runs_locally(path),
                said["runs_locally"].as_bool().unwrap(),
                "runs_locally {path} under {at}"
            );
            assert_eq!(
                router.swap(path).as_deref(),
                said["swap"].as_str(),
                "swap {path} under {at}"
            );
            checked += 1;
        }
        for (text, said) in case["texts"].as_object().unwrap() {
            assert_eq!(
                router.rewrite(text),
                said.as_str().unwrap(),
                "rewrite {text:?} under {at}"
            );
        }
    }
    assert!(checked > 1000);
}
