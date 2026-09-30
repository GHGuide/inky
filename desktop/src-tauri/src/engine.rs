//! Finding the Inky engine: attach to one that already runs on this data folder (engine.json), or read the
//! URL the sidecar prints when it starts. Two engines must never share one database.
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::Path;
use std::time::Duration;

/// "Inky is running at http://127.0.0.1:53211" -> "http://127.0.0.1:53211"
pub fn parse_url(line: &str) -> Option<String> {
    let rest = line.trim().strip_prefix("Inky is running at ")?;
    let url = rest.split_whitespace().next()?;
    (url.starts_with("http://127.0.0.1:") || url.starts_with("http://localhost:")).then(|| url.to_string())
}

/// An engine that already runs on `home`, if engine.json names one and it answers.
pub fn discover(home: &Path) -> Option<String> {
    let text = std::fs::read_to_string(home.join("engine.json")).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    let url = v.get("url")?.as_str()?.to_string();
    ping(&url).then_some(url)
}

/// GET /api/ping over a plain socket (no HTTP client needed for one local request).
pub fn ping(url: &str) -> bool {
    let Some(hostport) = url.strip_prefix("http://") else { return false };
    let Some(addr) = hostport.to_socket_addrs().ok().and_then(|mut a| a.next()) else { return false };
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(800)) else { return false };
    let _ = s.set_read_timeout(Some(Duration::from_millis(1500)));
    if s.write_all(format!("GET /api/ping HTTP/1.0\r\nHost: {hostport}\r\n\r\n").as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    let n = s.read(&mut buf).unwrap_or(0);
    String::from_utf8_lossy(&buf[..n]).split_whitespace().nth(1) == Some("200")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_the_url_the_engine_prints() {
        assert_eq!(parse_url("Inky is running at http://127.0.0.1:53211\n").as_deref(), Some("http://127.0.0.1:53211"));
        assert_eq!(parse_url("Pairing code for other computers: ABC123"), None);
        assert_eq!(parse_url("Inky is running at http://evil.example:80"), None);
    }

    #[test]
    fn no_engine_file_means_start_one() {
        let dir = std::env::temp_dir().join(format!("inky-discover-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(discover(&dir), None);
        std::fs::write(dir.join("engine.json"), r#"{"url": "http://127.0.0.1:1", "pid": 1}"#).unwrap();
        assert_eq!(discover(&dir), None); // nothing answers there
        std::fs::remove_dir_all(&dir).ok();
    }
}
