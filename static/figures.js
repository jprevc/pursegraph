// How amounts read in the browser: the twin of pursegraph/figures.py (DESIGN.md, the Locale Figure Rule).
// tests/test_figures.py runs both on the same values, so a chart's "1.234,56 €" is the table's.
(() => {
  const euros = (digits, signDisplay = 'negative') => new Intl.NumberFormat('sl-SI', {
    style: 'currency', currency: 'EUR', useGrouping: 'always',
    minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay,
  });
  const cents = euros(2), whole = euros(0), signed = euros(2, 'exceptZero');
  const percent = new Intl.NumberFormat('sl-SI', { style: 'percent', maximumFractionDigits: 0, signDisplay: 'negative' });

  window.Figures = {
    money: v => cents.format(v),
    moneyWhole: v => whole.format(v),
    // Net, with its sign always shown.
    moneySigned: v => signed.format(v),
    // A fraction as whole percent: 0.256 is "26 %".
    share: v => percent.format(v),
  };
})();
