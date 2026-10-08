# Third-party notices

DELPHI adapts **Machine Learning: Lorentzian Classification** by **jdehorty**. The source retains the original attribution and MPL 2.0 notice.

- Original work: feature engineering, approximate neighbor search, prediction filters, kernel regression, signal and exit rules.
- Pine dependencies: `jdehorty/MLExtensions/2` and `jdehorty/KernelFunctions/2`.
- License: [Mozilla Public License 2.0](LICENSE).
- DELPHI changes: TradingView strategy orders, New York session cutoff, order alerts, and JXS branding.

KAIROS V4 adds optional LC classification and ML vote confirmation to V3's kernel strategy, plus EMA/SMA gates. Its normalized RSI/WT/CCI/ADX features, logarithmic distance, published four-bar label signs and chronological ANN-style acceptance are adapted from jdehorty. The V4 adaptation uses bounded rolling training buffers, expires old votes, excludes the current query from candidates and guards against duplicate samples on fill callbacks. These changes are documented in [V4 usage](KAIROS_V4_Usage.md); V3 remains available unchanged.

The source code is distributed under MPL 2.0.

