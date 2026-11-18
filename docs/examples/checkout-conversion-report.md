# Checkout Conversion Drop

Rule-based demo — no LLM involved

**Run:** 6955a2cd-d79c-4102-bfb3-63ac6bc9385e  
**Source:** Northstar Shop (synthetic), northstar-2  
**UTC scope:** 2025-10-18 to 2025-10-20 vs. 2025-10-21 to 2025-10-23 (all)  
**Assessment confidence:** moderate

## Payment authentication is the leading hypothesis

### Observation · Checkout conversion

Conversion moved from 82.86% (870/1,050) to 68.86% (723/1,050), a change of -14.00 percentage points. [ev-3ea4fecd86afcdb6cb443227](#source-ev-3ea4fecd86afcdb6cb443227)

### Observation · Sessions and orders

Sessions went from 6,000 to 6,000. Completed purchases went from 870 to 723. [ev-44810d83e23974b971dc074f](#source-ev-44810d83e23974b971dc074f) [ev-019371934f97182ff3c83787](#source-ev-019371934f97182ff3c83787)

### Observation · Segment movement

Mobile 80.00% to 48.00%, with 450 to 450 starts. Web 85.00% to 84.50%, with 600 to 600 starts. [ev-3ea4fecd86afcdb6cb443227](#source-ev-3ea4fecd86afcdb6cb443227)

### Observation · Payment failures

Recorded payment failures went from 180/1,050 (17.14%) to 327/1,050 (31.14%). [ev-50504999e923099c054a666a](#source-ev-50504999e923099c054a666a) [ev-06a095da505b311206ae9c81](#source-ev-06a095da505b311206ae9c81)

### Observation · Authentication timeouts

Mobile card timeouts went from 0 to 180. [ev-50504999e923099c054a666a](#source-ev-50504999e923099c054a666a) [ev-06a095da505b311206ae9c81](#source-ev-06a095da505b311206ae9c81)

### Observation · Deployment timeline

v4.21 at 2025-10-21 09:00 UTC. [ev-863f626632eb2a7c57fc2f3f](#source-ev-863f626632eb2a7c57fc2f3f)

### Observation · Flag exposure

card_auth_v2 reached 50% of the mobile segment. [ev-4708fedc62638ba2309452a3](#source-ev-4708fedc62638ba2309452a3)

### Observation · Support signals

Recorded tickets went from 6 to 21. Category counts: payment failure 3 to 18, shipping 3 to 3. [ev-4c52217f83b71760eba18df9](#source-ev-4c52217f83b71760eba18df9) [ev-93706fc3058ee4b50879f891](#source-ev-93706fc3058ee4b50879f891)

### Hypothesis · Payment authentication is the leading hypothesis

Conversion fell alongside concentrated authentication timeouts in the affected window. [ev-3ea4fecd86afcdb6cb443227](#source-ev-3ea4fecd86afcdb6cb443227) [ev-44810d83e23974b971dc074f](#source-ev-44810d83e23974b971dc074f) [ev-019371934f97182ff3c83787](#source-ev-019371934f97182ff3c83787) [ev-50504999e923099c054a666a](#source-ev-50504999e923099c054a666a) [ev-06a095da505b311206ae9c81](#source-ev-06a095da505b311206ae9c81) [ev-863f626632eb2a7c57fc2f3f](#source-ev-863f626632eb2a7c57fc2f3f) [ev-4708fedc62638ba2309452a3](#source-ev-4708fedc62638ba2309452a3) [ev-4c52217f83b71760eba18df9](#source-ev-4c52217f83b71760eba18df9) [ev-93706fc3058ee4b50879f891](#source-ev-93706fc3058ee4b50879f891)

## Limitations

- The windows show an association. Exposure cohorts or controlled tests are needed to establish causality.
- Source records belong to the fictional Northstar Shop dataset.
- Support records reflect reporting behavior and provide limited coverage of all shoppers.

## Unresolved questions

- Which affected and unaffected cohorts can independently validate this assessment?

## Next actions

- Compare payment outcomes by flag exposure and verify with provider logs.

## Evidence

<a id="source-ev-019371934f97182ff3c83787"></a>
**ev-019371934f97182ff3c83787** · get_metric_summary

`traffic-2025-10-21-mobile`, `traffic-2025-10-21-web`, `traffic-2025-10-22-mobile`, `traffic-2025-10-22-web`, `traffic-2025-10-23-mobile`, `traffic-2025-10-23-web`

<a id="source-ev-06a095da505b311206ae9c81"></a>
**ev-06a095da505b311206ae9c81** · get_payment_error_breakdown

`pay-2025-10-21-mobile-card-approved`, `pay-2025-10-21-mobile-card-authentication_timeout`, `pay-2025-10-21-mobile-card-declined`, `pay-2025-10-21-mobile-wallet-approved`, `pay-2025-10-21-mobile-wallet-declined`, `pay-2025-10-21-web-card-approved`, `pay-2025-10-21-web-card-declined`, `pay-2025-10-21-web-wallet-approved`, `pay-2025-10-21-web-wallet-declined`, `pay-2025-10-22-mobile-card-approved`, `pay-2025-10-22-mobile-card-authentication_timeout`, `pay-2025-10-22-mobile-card-declined`, `pay-2025-10-22-mobile-wallet-approved`, `pay-2025-10-22-mobile-wallet-declined`, `pay-2025-10-22-web-card-approved`, `pay-2025-10-22-web-card-declined`, `pay-2025-10-22-web-wallet-approved`, `pay-2025-10-22-web-wallet-declined`, `pay-2025-10-23-mobile-card-approved`, `pay-2025-10-23-mobile-card-authentication_timeout`, `pay-2025-10-23-mobile-card-declined`, `pay-2025-10-23-mobile-wallet-approved`, `pay-2025-10-23-mobile-wallet-declined`, `pay-2025-10-23-web-card-approved`, `pay-2025-10-23-web-card-declined`, `pay-2025-10-23-web-wallet-approved`, `pay-2025-10-23-web-wallet-declined`

<a id="source-ev-3ea4fecd86afcdb6cb443227"></a>
**ev-3ea4fecd86afcdb6cb443227** · compare_time_windows

`traffic-2025-10-18-mobile`, `traffic-2025-10-18-web`, `traffic-2025-10-19-mobile`, `traffic-2025-10-19-web`, `traffic-2025-10-20-mobile`, `traffic-2025-10-20-web`, `traffic-2025-10-21-mobile`, `traffic-2025-10-21-web`, `traffic-2025-10-22-mobile`, `traffic-2025-10-22-web`, `traffic-2025-10-23-mobile`, `traffic-2025-10-23-web`

<a id="source-ev-44810d83e23974b971dc074f"></a>
**ev-44810d83e23974b971dc074f** · get_metric_summary

`traffic-2025-10-18-mobile`, `traffic-2025-10-18-web`, `traffic-2025-10-19-mobile`, `traffic-2025-10-19-web`, `traffic-2025-10-20-mobile`, `traffic-2025-10-20-web`

<a id="source-ev-4708fedc62638ba2309452a3"></a>
**ev-4708fedc62638ba2309452a3** · list_feature_flag_changes

`flag-card_auth_v2`

<a id="source-ev-4c52217f83b71760eba18df9"></a>
**ev-4c52217f83b71760eba18df9** · get_support_category_trends

`ticket-2025-10-18-payment_failure-01`, `ticket-2025-10-18-shipping-01`, `ticket-2025-10-19-payment_failure-01`, `ticket-2025-10-19-shipping-01`, `ticket-2025-10-20-payment_failure-01`, `ticket-2025-10-20-shipping-01`

<a id="source-ev-50504999e923099c054a666a"></a>
**ev-50504999e923099c054a666a** · get_payment_error_breakdown

`pay-2025-10-18-mobile-card-approved`, `pay-2025-10-18-mobile-card-declined`, `pay-2025-10-18-mobile-wallet-approved`, `pay-2025-10-18-mobile-wallet-declined`, `pay-2025-10-18-web-card-approved`, `pay-2025-10-18-web-card-declined`, `pay-2025-10-18-web-wallet-approved`, `pay-2025-10-18-web-wallet-declined`, `pay-2025-10-19-mobile-card-approved`, `pay-2025-10-19-mobile-card-declined`, `pay-2025-10-19-mobile-wallet-approved`, `pay-2025-10-19-mobile-wallet-declined`, `pay-2025-10-19-web-card-approved`, `pay-2025-10-19-web-card-declined`, `pay-2025-10-19-web-wallet-approved`, `pay-2025-10-19-web-wallet-declined`, `pay-2025-10-20-mobile-card-approved`, `pay-2025-10-20-mobile-card-declined`, `pay-2025-10-20-mobile-wallet-approved`, `pay-2025-10-20-mobile-wallet-declined`, `pay-2025-10-20-web-card-approved`, `pay-2025-10-20-web-card-declined`, `pay-2025-10-20-web-wallet-approved`, `pay-2025-10-20-web-wallet-declined`

<a id="source-ev-863f626632eb2a7c57fc2f3f"></a>
**ev-863f626632eb2a7c57fc2f3f** · list_releases

`rel-v4-21`

<a id="source-ev-93706fc3058ee4b50879f891"></a>
**ev-93706fc3058ee4b50879f891** · get_support_category_trends

`ticket-2025-10-21-payment_failure-01`, `ticket-2025-10-21-payment_failure-02`, `ticket-2025-10-21-payment_failure-03`, `ticket-2025-10-21-payment_failure-04`, `ticket-2025-10-21-payment_failure-05`, `ticket-2025-10-21-payment_failure-06`, `ticket-2025-10-21-shipping-01`, `ticket-2025-10-22-payment_failure-01`, `ticket-2025-10-22-payment_failure-02`, `ticket-2025-10-22-payment_failure-03`, `ticket-2025-10-22-payment_failure-04`, `ticket-2025-10-22-payment_failure-05`, `ticket-2025-10-22-payment_failure-06`, `ticket-2025-10-22-shipping-01`, `ticket-2025-10-23-payment_failure-01`, `ticket-2025-10-23-payment_failure-02`, `ticket-2025-10-23-payment_failure-03`, `ticket-2025-10-23-payment_failure-04`, `ticket-2025-10-23-payment_failure-05`, `ticket-2025-10-23-payment_failure-06`, `ticket-2025-10-23-shipping-01`

## Review history

- Round 1 · approve · 2026-11-18 05:41:44.866600+00:00
  - Reviewer note: Verified the funnel denominators and payment evidence\.
