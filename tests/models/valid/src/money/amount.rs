pub struct Amount(i64);

impl Amount {
    pub fn add(&self, other: &Amount) -> Amount {
        Amount(self.0 + other.0)
    }
}
