use anyhow::Result;
use std::time::Duration;
use tracing::warn;

pub struct RetryPolicy {
    pub max_attempts: usize,
    pub initial_delay: Duration,
    pub max_delay: Duration,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            max_attempts: 5,
            initial_delay: Duration::from_secs(1),
            max_delay: Duration::from_secs(120),
        }
    }
}

impl RetryPolicy {
    pub async fn execute<F, T, E>(&self, mut op: F) -> Result<T, E>
    where
        F: FnMut() -> Result<T, E>,
        E: std::fmt::Display,
    {
        let mut attempt = 0;
        let mut delay = self.initial_delay;

        loop {
            attempt += 1;
            match op() {
                Ok(val) => return Ok(val),
                Err(err) => {
                    if attempt >= self.max_attempts {
                        return Err(err);
                    }
                    warn!(
                        "Attempt {}/{} failed: {}. Retrying in {:?}...",
                        attempt, self.max_attempts, err, delay
                    );
                    tokio::time::sleep(delay).await;
                    delay = (delay * 2).min(self.max_delay);
                }
            }
        }
    }
}
