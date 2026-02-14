const UPBCASH_SALDO_KEY = "upbcash_saldo";

function getUpbcashSaldo() {
  return Number(localStorage.getItem(UPBCASH_SALDO_KEY) ?? 0);
}

function setUpbcashSaldo(value) {
  localStorage.setItem(UPBCASH_SALDO_KEY, String(Number(value) || 0));
}

function formatUpbcashCurrency(value) {
  return `$${Number(value).toFixed(2)}`;
}

function updateUpbcashSaldoText(selector) {
  const el = document.querySelector(selector);
  if (!el) return;
  el.textContent = formatUpbcashCurrency(getUpbcashSaldo());
}
