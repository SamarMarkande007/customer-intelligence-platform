-- =====================================================================================
--  NETFLIX CUSTOMER INTELLIGENCE: 37 SQL BUSINESS QUESTIONS   (MySQL 8.0)
--  Database: netflix_ci   (run schema.sql + load_data.py first)
--
--  CONVENTIONS USED IN EVERY QUERY
--  * "Active customer"      = churn_labels.churned = 0  (identical to customers whose subscription is 'Active')
--  * "Current plan"         = the customer's most recent subscriptions row (latest subscription_start_date)
--  * "Today" / reference    = 2026-06-30 (latest date in viewing, tickets, feedback and churn data)
--  * Payments stop on 2026-05-31, so payment-based "last N days / months" windows are anchored on
--    MAX(payment_date) instead of the reference date. This avoids an empty final month.
--  * Revenue / lifetime value = SUM(amount) of payment_status = 'Success' (amount is the cleaned value)
--  * Viewing history only covers 2025-07-01 .. 2026-06-30 (12 months)
--  * Time windows that are written as literal dates are marked "-- window:" so you can see what to change
--  * Tip: in MySQL Workbench select ONE query and press Ctrl+Enter to run just that one
-- =====================================================================================
USE netflix_ci;


-- #####################################################################################
-- SECTION A: INTERMEDIATE  (Q01 - Q15)
-- #####################################################################################

-- ===== Q01: Active customers by country =====
SELECT c.country,
       COUNT(*) AS active_customers
FROM customers c
JOIN churn_labels cl ON cl.customer_id = c.customer_id
WHERE cl.churned = 0
GROUP BY c.country
ORDER BY active_customers DESC;


-- ===== Q02: Total and average monthly revenue by subscription plan =====
-- avg_monthly_revenue = average of the plan's revenue across the calendar months in which it was billed
WITH plan_month AS (
    SELECT s.plan_id,
           DATE_FORMAT(p.payment_date, '%Y-%m') AS ym,
           SUM(p.amount)                         AS revenue
    FROM payments p
    JOIN subscriptions s ON s.subscription_id = p.subscription_id
    WHERE p.payment_status = 'Success'
    GROUP BY s.plan_id, DATE_FORMAT(p.payment_date, '%Y-%m')
)
SELECT sp.plan_name,
       ROUND(SUM(pm.revenue), 2) AS total_revenue,
       ROUND(AVG(pm.revenue), 2) AS avg_monthly_revenue,
       COUNT(*)                  AS months_billed
FROM plan_month pm
JOIN subscription_plans sp ON sp.plan_id = pm.plan_id
GROUP BY sp.plan_id, sp.plan_name
ORDER BY total_revenue DESC;


-- ===== Q03: Overall churn rate =====
SELECT COUNT(*)                          AS total_customers,
       SUM(churned)                      AS churned_customers,
       ROUND(100 * AVG(churned), 2)      AS churn_rate_pct
FROM churn_labels;


-- ===== Q04: Customers acquired and churn rate per acquisition channel =====
SELECT c.acquisition_channel,
       COUNT(*)                          AS customers_acquired,
       SUM(cl.churned)                   AS churned_customers,
       ROUND(100 * AVG(cl.churned), 2)   AS churn_rate_pct
FROM customers c
JOIN churn_labels cl ON cl.customer_id = c.customer_id
GROUP BY c.acquisition_channel
ORDER BY customers_acquired DESC;


-- ===== Q05: Average customer age by (current) subscription plan =====
WITH current_sub AS (
    SELECT s.customer_id, s.plan_id,
           ROW_NUMBER() OVER (PARTITION BY s.customer_id
                              ORDER BY s.subscription_start_date DESC, s.subscription_id DESC) AS rn
    FROM subscriptions s
)
SELECT sp.plan_name,
       COUNT(*)              AS customers,
       ROUND(AVG(c.age), 1)  AS avg_age
FROM current_sub cs
JOIN customers c           ON c.customer_id = cs.customer_id
JOIN subscription_plans sp ON sp.plan_id    = cs.plan_id
WHERE cs.rn = 1
GROUP BY sp.plan_id, sp.plan_name
ORDER BY sp.plan_id;


-- ===== Q06: Top 10 most-watched titles by total watch minutes =====
SELECT ct.content_id,
       ct.title,
       ct.content_type,
       ct.genre,
       SUM(v.watch_duration_minutes) AS total_watch_minutes,
       COUNT(*)                      AS sessions
FROM viewing_activity v
JOIN content ct ON ct.content_id = v.content_id
GROUP BY ct.content_id, ct.title, ct.content_type, ct.genre
ORDER BY total_watch_minutes DESC
LIMIT 10;


-- ===== Q07: Average completion % by content_type and genre =====
SELECT ct.content_type,
       ct.genre,
       ROUND(AVG(v.completion_percentage), 2) AS avg_completion_pct,
       COUNT(*)                               AS sessions
FROM viewing_activity v
JOIN content ct ON ct.content_id = v.content_id
GROUP BY ct.content_type, ct.genre
ORDER BY ct.content_type, avg_completion_pct DESC;


-- ===== Q08: Failed payments in each of the last 12 months =====
-- window: 12 months ending at the latest payment date in the table (2026-05-31)
SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month,
       COUNT(*)                           AS failed_payments
FROM payments
WHERE payment_status = 'Failed'
  AND payment_date > DATE_SUB((SELECT MAX(payment_date) FROM payments), INTERVAL 12 MONTH)
GROUP BY DATE_FORMAT(payment_date, '%Y-%m')
ORDER BY payment_month;


-- ===== Q09: Average resolution time (hours) by issue category =====
SELECT issue_category,
       COUNT(*)                            AS resolved_tickets,
       ROUND(AVG(resolution_time_hours), 1) AS avg_resolution_hours
FROM support_tickets
WHERE resolution_time_hours IS NOT NULL
GROUP BY issue_category
ORDER BY avg_resolution_hours DESC;


-- ===== Q10: Distribution of CSAT score across resolved / closed tickets =====
SELECT customer_satisfaction_score AS csat_score,
       COUNT(*)                                          AS tickets,
       ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)  AS pct_of_tickets
FROM support_tickets
WHERE ticket_status IN ('Resolved', 'Closed')
  AND customer_satisfaction_score IS NOT NULL
GROUP BY customer_satisfaction_score
ORDER BY csat_score;


-- ===== Q11: Device type generating the most viewing minutes =====
SELECT device_type,
       SUM(watch_duration_minutes)                                       AS total_watch_minutes,
       ROUND(100 * SUM(watch_duration_minutes) / SUM(SUM(watch_duration_minutes)) OVER (), 2) AS pct_of_total
FROM viewing_activity
GROUP BY device_type
ORDER BY total_watch_minutes DESC;


-- ===== Q12: Average rating by sentiment label =====
-- sentiment_label is the CLEANED label (re-derived from rating and validated against the text)
SELECT sentiment_label,
       COUNT(*)              AS feedback_entries,
       ROUND(AVG(rating), 2) AS avg_rating
FROM customer_feedback
GROUP BY sentiment_label
ORDER BY avg_rating DESC;


-- ===== Q13: Customers signed up per acquisition channel in each calendar year (pivot) =====
SELECT acquisition_channel,
       SUM(YEAR(registration_date) = 2019) AS y2019,
       SUM(YEAR(registration_date) = 2020) AS y2020,
       SUM(YEAR(registration_date) = 2021) AS y2021,
       SUM(YEAR(registration_date) = 2022) AS y2022,
       SUM(YEAR(registration_date) = 2023) AS y2023,
       SUM(YEAR(registration_date) = 2024) AS y2024,
       SUM(YEAR(registration_date) = 2025) AS y2025,
       SUM(YEAR(registration_date) = 2026) AS y2026_ytd,
       COUNT(*)                            AS total
FROM customers
GROUP BY acquisition_channel
ORDER BY total DESC;


-- ===== Q14: % of customers with auto-renew turned off (current subscription) =====
WITH current_sub AS (
    SELECT s.customer_id, s.auto_renew,
           ROW_NUMBER() OVER (PARTITION BY s.customer_id
                              ORDER BY s.subscription_start_date DESC, s.subscription_id DESC) AS rn
    FROM subscriptions s
)
SELECT COUNT(*)                               AS customers,
       SUM(auto_renew = 0)                    AS auto_renew_off,
       ROUND(100 * AVG(auto_renew = 0), 2)    AS pct_auto_renew_off
FROM current_sub
WHERE rn = 1;


-- ===== Q15: Customers with more than 3 support tickets =====
SELECT t.customer_id,
       COUNT(*) AS ticket_count
FROM support_tickets t
GROUP BY t.customer_id
HAVING COUNT(*) > 3
ORDER BY ticket_count DESC, t.customer_id;


-- #####################################################################################
-- SECTION B: ADVANCED  (Q16 - Q27)
-- #####################################################################################

-- ===== Q16: RANK() plans by revenue = monthly_price x active subscriptions =====
WITH active_subs AS (
    SELECT plan_id, COUNT(*) AS active_subscriptions
    FROM subscriptions
    WHERE subscription_status = 'Active'
    GROUP BY plan_id
)
SELECT RANK() OVER (ORDER BY sp.monthly_price * a.active_subscriptions DESC) AS revenue_rank,
       sp.plan_name,
       sp.monthly_price,
       a.active_subscriptions,
       ROUND(sp.monthly_price * a.active_subscriptions, 2)                  AS monthly_recurring_revenue
FROM active_subs a
JOIN subscription_plans sp ON sp.plan_id = a.plan_id
ORDER BY revenue_rank;


-- ===== Q17: Most recent support ticket per customer (ROW_NUMBER) =====
WITH ranked AS (
    SELECT t.*,
           ROW_NUMBER() OVER (PARTITION BY t.customer_id
                              ORDER BY t.ticket_date DESC, t.ticket_id DESC) AS rn
    FROM support_tickets t
    WHERE t.ticket_date IS NOT NULL
)
SELECT customer_id, ticket_id, ticket_date, issue_category, issue_subcategory,
       priority, ticket_status, customer_satisfaction_score
FROM ranked
WHERE rn = 1
ORDER BY customer_id;


-- ===== Q18: 3-month moving average of new customer registrations =====
WITH monthly AS (
    SELECT DATE_FORMAT(registration_date, '%Y-%m') AS reg_month,
           COUNT(*)                                AS new_customers
    FROM customers
    GROUP BY DATE_FORMAT(registration_date, '%Y-%m')
)
SELECT reg_month,
       new_customers,
       ROUND(AVG(new_customers) OVER (ORDER BY reg_month
                                      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_3m
FROM monthly
ORDER BY reg_month;


-- ===== Q19: Month-over-month watch-time decline flag using LAG() =====
-- Compares the latest month in viewing_activity with the month before it.
-- A dense customer x month grid is used so a month with zero viewing counts as 0 (and not as a missing row).
-- Only customers still subscribed at the start of the prior month are considered.
WITH bounds AS (
    SELECT CAST(DATE_FORMAT(MAX(viewing_date), '%Y-%m-01') AS DATE) AS latest_month
    FROM viewing_activity
),
months AS (
    SELECT DATE_SUB(latest_month, INTERVAL 1 MONTH) AS month_start FROM bounds
    UNION ALL
    SELECT latest_month FROM bounds
),
eligible AS (
    SELECT c.customer_id
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
    CROSS JOIN bounds b
    WHERE cl.churned = 0 OR cl.churn_date >= DATE_SUB(b.latest_month, INTERVAL 1 MONTH)
),
grid AS (
    SELECT e.customer_id, m.month_start
    FROM eligible e CROSS JOIN months m
),
monthly AS (
    SELECT customer_id,
           CAST(DATE_FORMAT(viewing_date, '%Y-%m-01') AS DATE) AS month_start,
           SUM(watch_duration_minutes)                          AS watch_min
    FROM viewing_activity
    GROUP BY customer_id, CAST(DATE_FORMAT(viewing_date, '%Y-%m-01') AS DATE)
),
series AS (
    SELECT g.customer_id, g.month_start, COALESCE(m.watch_min, 0) AS watch_min
    FROM grid g
    LEFT JOIN monthly m ON m.customer_id = g.customer_id AND m.month_start = g.month_start
),
lagged AS (
    SELECT customer_id, month_start, watch_min,
           LAG(watch_min) OVER (PARTITION BY customer_id ORDER BY month_start) AS prior_month_min
    FROM series
)
SELECT l.customer_id,
       l.prior_month_min,
       l.watch_min                                                         AS latest_month_min,
       l.watch_min - l.prior_month_min                                     AS change_min,
       ROUND(100 * (l.watch_min - l.prior_month_min) / l.prior_month_min, 1) AS change_pct,
       1                                                                   AS decline_flag
FROM lagged l
JOIN bounds b ON b.latest_month = l.month_start
WHERE l.prior_month_min IS NOT NULL
  AND l.prior_month_min > 0
  AND l.watch_min < l.prior_month_min
ORDER BY change_pct;


-- ===== Q20: Registration-cohort retention at 1, 3 and 6 months =====
-- A customer is "still active at k months" if they have not churned by registration_date + k months.
-- A customer only counts toward a horizon once that horizon has elapsed by the reference date (2026-06-30),
-- so young cohorts show NULL instead of a misleading 100%.
-- window: reference date 2026-06-30
WITH base AS (
    SELECT c.customer_id,
           DATE_FORMAT(c.registration_date, '%Y-%m') AS cohort_month,
           c.registration_date,
           cl.churn_date
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
),
flags AS (
    SELECT cohort_month,
           (DATE_ADD(registration_date, INTERVAL 1 MONTH) <= '2026-06-30') AS elig_1,
           (DATE_ADD(registration_date, INTERVAL 3 MONTH) <= '2026-06-30') AS elig_3,
           (DATE_ADD(registration_date, INTERVAL 6 MONTH) <= '2026-06-30') AS elig_6,
           (churn_date IS NULL OR churn_date > DATE_ADD(registration_date, INTERVAL 1 MONTH)) AS alive_1,
           (churn_date IS NULL OR churn_date > DATE_ADD(registration_date, INTERVAL 3 MONTH)) AS alive_3,
           (churn_date IS NULL OR churn_date > DATE_ADD(registration_date, INTERVAL 6 MONTH)) AS alive_6
    FROM base
)
SELECT cohort_month,
       COUNT(*) AS cohort_size,
       ROUND(100 * SUM(elig_1 * alive_1) / NULLIF(SUM(elig_1), 0), 1) AS retained_1m_pct,
       ROUND(100 * SUM(elig_3 * alive_3) / NULLIF(SUM(elig_3), 0), 1) AS retained_3m_pct,
       ROUND(100 * SUM(elig_6 * alive_6) / NULLIF(SUM(elig_6), 0), 1) AS retained_6m_pct
FROM flags
GROUP BY cohort_month
ORDER BY cohort_month;


-- ===== Q21: DENSE_RANK() countries by churn rate, top 5 =====
WITH country_churn AS (
    SELECT c.country,
           COUNT(*)           AS customers,
           SUM(cl.churned)    AS churned_customers,
           AVG(cl.churned)    AS churn_rate
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
    GROUP BY c.country
),
ranked AS (
    SELECT country, customers, churned_customers, churn_rate,
           DENSE_RANK() OVER (ORDER BY churn_rate DESC) AS churn_rank
    FROM country_churn
)
SELECT churn_rank, country, customers, churned_customers,
       ROUND(100 * churn_rate, 2) AS churn_rate_pct
FROM ranked
WHERE churn_rank <= 5
ORDER BY churn_rank, country;


-- ===== Q22: Running total of successful payments per customer =====
-- (large result: ~103k rows. Workbench shows the first 1,000 by default)
SELECT customer_id,
       payment_id,
       payment_date,
       amount,
       ROUND(SUM(amount) OVER (PARTITION BY customer_id
                               ORDER BY payment_date, payment_id
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_total
FROM payments
WHERE payment_status = 'Success'
ORDER BY customer_id, payment_date, payment_id;


-- ===== Q23: Customers whose monthly watch time fell 3 months in a row (N < N-1 < N-2) =====
-- Dense customer x month grid over the 12 months of viewing data (0 minutes = no viewing).
-- Only months inside the customer's life (registered, and not yet churned) are included.
-- window: 2025-07-01 .. 2026-06-30
WITH RECURSIVE months AS (
    SELECT DATE('2025-07-01') AS month_start
    UNION ALL
    SELECT DATE_ADD(month_start, INTERVAL 1 MONTH) FROM months WHERE month_start < DATE('2026-06-01')
),
grid AS (
    SELECT c.customer_id, m.month_start
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
    CROSS JOIN months m
    WHERE c.registration_date < DATE_ADD(m.month_start, INTERVAL 1 MONTH)
      AND (cl.churn_date IS NULL OR cl.churn_date >= m.month_start)
),
monthly AS (
    SELECT customer_id,
           CAST(DATE_FORMAT(viewing_date, '%Y-%m-01') AS DATE) AS month_start,
           SUM(watch_duration_minutes)                          AS watch_min
    FROM viewing_activity
    GROUP BY customer_id, CAST(DATE_FORMAT(viewing_date, '%Y-%m-01') AS DATE)
),
series AS (
    SELECT g.customer_id, g.month_start, COALESCE(m.watch_min, 0) AS watch_min
    FROM grid g
    LEFT JOIN monthly m ON m.customer_id = g.customer_id AND m.month_start = g.month_start
),
lagged AS (
    SELECT customer_id, month_start, watch_min,
           LAG(watch_min, 1) OVER (PARTITION BY customer_id ORDER BY month_start) AS min_n1,
           LAG(watch_min, 2) OVER (PARTITION BY customer_id ORDER BY month_start) AS min_n2
    FROM series
)
SELECT customer_id,
       COUNT(*)         AS declining_windows,
       MAX(month_start) AS latest_decline_month
FROM lagged
WHERE min_n2 IS NOT NULL
  AND watch_min < min_n1
  AND min_n1   < min_n2
GROUP BY customer_id
ORDER BY declining_windows DESC, latest_decline_month DESC, customer_id;


-- ===== Q24: Monthly churn rate over the last 12 months =====
-- churn rate = customers who churned in month X / customers active at the START of month X
-- window: 2025-07 .. 2026-06
WITH RECURSIVE months AS (
    SELECT DATE('2025-07-01') AS month_start
    UNION ALL
    SELECT DATE_ADD(month_start, INTERVAL 1 MONTH) FROM months WHERE month_start < DATE('2026-06-01')
),
base AS (
    SELECT c.registration_date, cl.churn_date
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
)
SELECT DATE_FORMAT(m.month_start, '%Y-%m') AS month,
       COUNT(*)                            AS active_at_start,
       SUM(b.churn_date IS NOT NULL AND b.churn_date < DATE_ADD(m.month_start, INTERVAL 1 MONTH)) AS churned_in_month,
       ROUND(100 * SUM(b.churn_date IS NOT NULL AND b.churn_date < DATE_ADD(m.month_start, INTERVAL 1 MONTH)) / COUNT(*), 2) AS monthly_churn_rate_pct
FROM months m
JOIN base b ON b.registration_date < m.month_start
           AND (b.churn_date IS NULL OR b.churn_date >= m.month_start)
GROUP BY m.month_start
ORDER BY m.month_start;


-- ===== Q25: Retention rate by acquisition channel (% still active today) =====
SELECT c.acquisition_channel,
       COUNT(*)                                  AS customers_acquired,
       SUM(cl.churned = 0)                       AS still_active,
       ROUND(100 * AVG(cl.churned = 0), 2)       AS retention_rate_pct
FROM customers c
JOIN churn_labels cl ON cl.customer_id = c.customer_id
GROUP BY c.acquisition_channel
ORDER BY retention_rate_pct DESC;


-- ===== Q26: Lifetime spend per customer and NTILE(4) spend quartile =====
-- quartile 1 = highest-spending 25% of customers, quartile 4 = lowest
WITH spend AS (
    SELECT c.customer_id,
           COALESCE(SUM(CASE WHEN p.payment_status = 'Success' THEN p.amount END), 0) AS lifetime_spend
    FROM customers c
    LEFT JOIN payments p ON p.customer_id = c.customer_id
    GROUP BY c.customer_id
)
SELECT customer_id,
       ROUND(lifetime_spend, 2)                         AS lifetime_spend,
       NTILE(4) OVER (ORDER BY lifetime_spend DESC)     AS spend_quartile
FROM spend
ORDER BY lifetime_spend DESC, customer_id;

-- ===== Q26b: Quartile summary =====
WITH spend AS (
    SELECT c.customer_id,
           COALESCE(SUM(CASE WHEN p.payment_status = 'Success' THEN p.amount END), 0) AS lifetime_spend
    FROM customers c
    LEFT JOIN payments p ON p.customer_id = c.customer_id
    GROUP BY c.customer_id
),
q AS (
    SELECT customer_id, lifetime_spend,
           NTILE(4) OVER (ORDER BY lifetime_spend DESC) AS spend_quartile
    FROM spend
)
SELECT spend_quartile,
       COUNT(*)                       AS customers,
       ROUND(MIN(lifetime_spend), 2)  AS min_spend,
       ROUND(MAX(lifetime_spend), 2)  AS max_spend,
       ROUND(AVG(lifetime_spend), 2)  AS avg_spend,
       ROUND(SUM(lifetime_spend), 2)  AS total_spend
FROM q
GROUP BY spend_quartile
ORDER BY spend_quartile;


-- ===== Q27: Top 3 issue_subcategory by ticket volume per country (CTE + ROW_NUMBER) =====
WITH sub_counts AS (
    SELECT c.country, t.issue_subcategory, COUNT(*) AS tickets
    FROM support_tickets t
    JOIN customers c ON c.customer_id = t.customer_id
    GROUP BY c.country, t.issue_subcategory
),
ranked AS (
    SELECT country, issue_subcategory, tickets,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY tickets DESC, issue_subcategory) AS rn
    FROM sub_counts
)
SELECT country, rn AS position, issue_subcategory, tickets
FROM ranked
WHERE rn <= 3
ORDER BY country, rn;


-- #####################################################################################
-- SECTION C: EXPERT  (Q28 - Q37)
-- #####################################################################################

-- ===== Q28: 2+ failed payments in the last 90 days AND high churn risk =====
-- "High churn risk" = top quartile of the composite risk score among ACTIVE customers.
-- risk_score (0-1) = 0.40 x recency + 0.35 x failed-payment rate + 0.25 x ticket count
-- (each min-max normalised). This is the same score as Q31. Once the ML churn model exists,
-- replace risk_quartile = 1 with churn_risk_score >= your threshold.
-- window: last 90 days before the latest payment date (2026-05-31)
WITH current_sub AS (
    SELECT s.customer_id, s.plan_id,
           ROW_NUMBER() OVER (PARTITION BY s.customer_id
                              ORDER BY s.subscription_start_date DESC, s.subscription_id DESC) AS rn
    FROM subscriptions s
),
active AS (
    SELECT c.customer_id
    FROM customers c JOIN churn_labels cl ON cl.customer_id = c.customer_id
    WHERE cl.churned = 0
),
last_view AS (
    SELECT customer_id, MAX(viewing_date) AS last_view_date FROM viewing_activity GROUP BY customer_id
),
pay AS (
    SELECT customer_id, COUNT(*) AS payments, SUM(payment_status = 'Failed') AS failed_payments
    FROM payments GROUP BY customer_id
),
tix AS (
    SELECT customer_id, COUNT(*) AS ticket_count FROM support_tickets GROUP BY customer_id
),
metrics AS (
    SELECT a.customer_id,
           LEAST(COALESCE(DATEDIFF('2026-06-30', lv.last_view_date), 365), 365)     AS days_since_last_activity,
           COALESCE(p.failed_payments / NULLIF(p.payments, 0), 0)                   AS failed_payment_rate,
           COALESCE(t.ticket_count, 0)                                              AS support_ticket_count
    FROM active a
    LEFT JOIN last_view lv ON lv.customer_id = a.customer_id
    LEFT JOIN pay p        ON p.customer_id  = a.customer_id
    LEFT JOIN tix t        ON t.customer_id  = a.customer_id
),
bounds AS (
    SELECT MIN(days_since_last_activity) AS min_d, MAX(days_since_last_activity) AS max_d,
           MIN(failed_payment_rate)      AS min_f, MAX(failed_payment_rate)      AS max_f,
           MIN(support_ticket_count)     AS min_t, MAX(support_ticket_count)     AS max_t
    FROM metrics
),
normed AS (
    SELECT m.customer_id,
           COALESCE((m.days_since_last_activity - b.min_d) / NULLIF(b.max_d - b.min_d, 0), 0) AS recency_n,
           COALESCE((m.failed_payment_rate      - b.min_f) / NULLIF(b.max_f - b.min_f, 0), 0) AS failure_n,
           COALESCE((m.support_ticket_count     - b.min_t) / NULLIF(b.max_t - b.min_t, 0), 0) AS ticket_n
    FROM metrics m
    CROSS JOIN bounds b
),
scored AS (
    SELECT customer_id,
           0.40 * recency_n + 0.35 * failure_n + 0.25 * ticket_n AS risk_score,
           NTILE(4) OVER (ORDER BY 0.40 * recency_n + 0.35 * failure_n + 0.25 * ticket_n DESC) AS risk_quartile
    FROM normed
),
recent_failed AS (
    SELECT customer_id, COUNT(*) AS failed_payment_count
    FROM payments
    WHERE payment_status = 'Failed'
      AND payment_date > DATE_SUB((SELECT MAX(payment_date) FROM payments), INTERVAL 90 DAY)
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
)
SELECT rf.customer_id,
       rf.failed_payment_count,
       sp.plan_name AS current_plan,
       ROUND(sc.risk_score, 3) AS risk_score
FROM recent_failed rf
JOIN scored sc             ON sc.customer_id = rf.customer_id AND sc.risk_quartile = 1
JOIN current_sub cs        ON cs.customer_id = rf.customer_id AND cs.rn = 1
JOIN subscription_plans sp ON sp.plan_id     = cs.plan_id
ORDER BY rf.failed_payment_count DESC, sc.risk_score DESC, rf.customer_id;


-- ===== Q29: Engagement 30 days before vs 30 days after each customer's latest price change =====
-- DATA NOTE: subscriptions.monthly_price never differs inside one customer, because the old segment
-- carries the new plan's billed price. A "price change" is therefore a PLAN SWITCH whose list price
-- (subscription_plans.monthly_price) differs from the previous plan. The switch date = start date of the new row.
-- Engagement = average watch_duration_minutes per session. Only customers with sessions in BOTH windows are reported
-- (viewing data starts 2025-07-01, so older changes have no data).
WITH sub_prices AS (
    SELECT s.customer_id, s.subscription_start_date, sp.monthly_price AS list_price,
           LAG(sp.monthly_price) OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_price
    FROM subscriptions s
    JOIN subscription_plans sp ON sp.plan_id = s.plan_id
),
changes AS (
    SELECT customer_id, subscription_start_date AS change_date, list_price, prev_price,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY subscription_start_date DESC) AS rn
    FROM sub_prices
    WHERE prev_price IS NOT NULL AND list_price <> prev_price
),
latest_change AS (
    SELECT * FROM changes WHERE rn = 1
),
eng AS (
    SELECT lc.customer_id, lc.change_date, lc.prev_price, lc.list_price,
           AVG(CASE WHEN v.viewing_date <  lc.change_date THEN v.watch_duration_minutes END) AS avg_before,
           AVG(CASE WHEN v.viewing_date >= lc.change_date THEN v.watch_duration_minutes END) AS avg_after,
           SUM(v.viewing_date <  lc.change_date) AS sessions_before,
           SUM(v.viewing_date >= lc.change_date) AS sessions_after
    FROM latest_change lc
    JOIN viewing_activity v
      ON v.customer_id = lc.customer_id
     AND v.viewing_date BETWEEN DATE_SUB(lc.change_date, INTERVAL 30 DAY) AND DATE_ADD(lc.change_date, INTERVAL 30 DAY)
    GROUP BY lc.customer_id, lc.change_date, lc.prev_price, lc.list_price
)
SELECT customer_id,
       change_date,
       CASE WHEN list_price > prev_price THEN 'Price increase' ELSE 'Price decrease' END AS price_direction,
       ROUND(avg_before, 1) AS avg_watch_min_before,
       ROUND(avg_after, 1)  AS avg_watch_min_after,
       sessions_before,
       sessions_after,
       ROUND(100 * (avg_after - avg_before) / avg_before, 1) AS pct_change
FROM eng
WHERE avg_before IS NOT NULL AND avg_after IS NOT NULL
ORDER BY change_date DESC, customer_id;

-- ===== Q29b: Summary of the above by price direction =====
WITH sub_prices AS (
    SELECT s.customer_id, s.subscription_start_date, sp.monthly_price AS list_price,
           LAG(sp.monthly_price) OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_price
    FROM subscriptions s
    JOIN subscription_plans sp ON sp.plan_id = s.plan_id
),
changes AS (
    SELECT customer_id, subscription_start_date AS change_date, list_price, prev_price,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY subscription_start_date DESC) AS rn
    FROM sub_prices
    WHERE prev_price IS NOT NULL AND list_price <> prev_price
),
latest_change AS (
    SELECT * FROM changes WHERE rn = 1
),
eng AS (
    SELECT lc.customer_id, lc.list_price, lc.prev_price,
           AVG(CASE WHEN v.viewing_date <  lc.change_date THEN v.watch_duration_minutes END) AS avg_before,
           AVG(CASE WHEN v.viewing_date >= lc.change_date THEN v.watch_duration_minutes END) AS avg_after
    FROM latest_change lc
    JOIN viewing_activity v
      ON v.customer_id = lc.customer_id
     AND v.viewing_date BETWEEN DATE_SUB(lc.change_date, INTERVAL 30 DAY) AND DATE_ADD(lc.change_date, INTERVAL 30 DAY)
    GROUP BY lc.customer_id, lc.list_price, lc.prev_price
)
SELECT CASE WHEN list_price > prev_price THEN 'Price increase' ELSE 'Price decrease' END AS price_direction,
       COUNT(*)                                                        AS customers,
       ROUND(AVG(avg_before), 1)                                       AS avg_watch_min_before,
       ROUND(AVG(avg_after), 1)                                        AS avg_watch_min_after,
       ROUND(100 * (AVG(avg_after) - AVG(avg_before)) / AVG(avg_before), 1) AS pct_change
FROM eng
WHERE avg_before IS NOT NULL AND avg_after IS NOT NULL
GROUP BY CASE WHEN list_price > prev_price THEN 'Price increase' ELSE 'Price decrease' END;


-- ===== Q30: Country scorecard: customers, churn, churn rate, avg CLV of churned customers, top churn reason =====
WITH cust AS (
    SELECT c.customer_id, c.country, cl.churned, cl.churn_reason
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
),
clv AS (
    SELECT customer_id, SUM(amount) AS lifetime_value
    FROM payments
    WHERE payment_status = 'Success'
    GROUP BY customer_id
),
country_stats AS (
    SELECT cu.country,
           COUNT(*)                                                              AS total_customers,
           SUM(cu.churned)                                                       AS churned_customers,
           AVG(cu.churned)                                                       AS churn_rate,
           AVG(CASE WHEN cu.churned = 1 THEN COALESCE(clv.lifetime_value, 0) END) AS avg_churned_clv
    FROM cust cu
    LEFT JOIN clv ON clv.customer_id = cu.customer_id
    GROUP BY cu.country
),
reason_counts AS (
    SELECT country, churn_reason, COUNT(*) AS n
    FROM cust
    WHERE churned = 1
    GROUP BY country, churn_reason
),
top_reason AS (
    SELECT country, churn_reason, n,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY n DESC, churn_reason) AS rn
    FROM reason_counts
)
SELECT s.country,
       s.total_customers,
       s.churned_customers,
       ROUND(100 * s.churn_rate, 2)  AS churn_rate_pct,
       ROUND(s.avg_churned_clv, 2)   AS avg_clv_churned_customer,
       t.churn_reason                AS top_churn_reason,
       t.n                           AS top_reason_customers
FROM country_stats s
LEFT JOIN top_reason t ON t.country = s.country AND t.rn = 1
ORDER BY churn_rate_pct DESC;


-- ===== Q31: "At-risk revenue" report: top 50 active customers =====
-- risk_score (0-1) = 0.40 x recency + 0.35 x failed-payment rate + 0.25 x ticket count, each min-max normalised across
-- active customers. recency = days since last viewing (customers with no viewing in the 12-month log = 365, the cap).
-- at_risk_revenue = risk_score x current monthly_price
WITH current_sub AS (
    SELECT s.customer_id, s.plan_id, s.monthly_price,
           ROW_NUMBER() OVER (PARTITION BY s.customer_id
                              ORDER BY s.subscription_start_date DESC, s.subscription_id DESC) AS rn
    FROM subscriptions s
),
active AS (
    SELECT c.customer_id
    FROM customers c JOIN churn_labels cl ON cl.customer_id = c.customer_id
    WHERE cl.churned = 0
),
last_view AS (
    SELECT customer_id, MAX(viewing_date) AS last_view_date FROM viewing_activity GROUP BY customer_id
),
pay AS (
    SELECT customer_id, COUNT(*) AS payments, SUM(payment_status = 'Failed') AS failed_payments
    FROM payments GROUP BY customer_id
),
tix AS (
    SELECT customer_id, COUNT(*) AS ticket_count FROM support_tickets GROUP BY customer_id
),
metrics AS (
    SELECT a.customer_id, cs.monthly_price, sp.plan_name,
           LEAST(COALESCE(DATEDIFF('2026-06-30', lv.last_view_date), 365), 365) AS days_since_last_activity,
           COALESCE(p.failed_payments / NULLIF(p.payments, 0), 0)               AS failed_payment_rate,
           COALESCE(t.ticket_count, 0)                                          AS support_ticket_count
    FROM active a
    JOIN current_sub cs        ON cs.customer_id = a.customer_id AND cs.rn = 1
    JOIN subscription_plans sp ON sp.plan_id = cs.plan_id
    LEFT JOIN last_view lv     ON lv.customer_id = a.customer_id
    LEFT JOIN pay p            ON p.customer_id  = a.customer_id
    LEFT JOIN tix t            ON t.customer_id  = a.customer_id
),
bounds AS (
    SELECT MIN(days_since_last_activity) AS min_d, MAX(days_since_last_activity) AS max_d,
           MIN(failed_payment_rate)      AS min_f, MAX(failed_payment_rate)      AS max_f,
           MIN(support_ticket_count)     AS min_t, MAX(support_ticket_count)     AS max_t
    FROM metrics
),
normed AS (
    SELECT m.*,
           COALESCE((m.days_since_last_activity - b.min_d) / NULLIF(b.max_d - b.min_d, 0), 0) AS recency_n,
           COALESCE((m.failed_payment_rate      - b.min_f) / NULLIF(b.max_f - b.min_f, 0), 0) AS failure_n,
           COALESCE((m.support_ticket_count     - b.min_t) / NULLIF(b.max_t - b.min_t, 0), 0) AS ticket_n
    FROM metrics m
    CROSS JOIN bounds b
),
scored AS (
    SELECT normed.*,
           0.40 * recency_n + 0.35 * failure_n + 0.25 * ticket_n AS risk_score
    FROM normed
)
SELECT RANK() OVER (ORDER BY risk_score * monthly_price DESC) AS at_risk_rank,
       customer_id,
       plan_name,
       monthly_price,
       days_since_last_activity,
       ROUND(failed_payment_rate, 3)       AS failed_payment_rate,
       support_ticket_count,
       ROUND(risk_score, 3)                AS risk_score,
       ROUND(risk_score * monthly_price, 2) AS at_risk_revenue
FROM scored
ORDER BY at_risk_revenue DESC, customer_id
LIMIT 50;


-- ===== Q32: Top 5 complaints per country, most recent completed quarter =====
-- window: 2026 Q2 (2026-04-01 .. 2026-06-30). The data ends on 2026-06-30, so Q2 2026 is the latest complete quarter.
-- Avg resolution time and CSAT are computed over the tickets of that subcategory in that country and quarter
-- (open tickets have no resolution time / CSAT and are ignored by AVG).
WITH q AS (
    SELECT c.country,
           t.issue_subcategory,
           COUNT(*)                                  AS tickets,
           ROUND(AVG(t.resolution_time_hours), 1)    AS avg_resolution_hours,
           ROUND(AVG(t.customer_satisfaction_score), 2) AS avg_csat
    FROM support_tickets t
    JOIN customers c ON c.customer_id = t.customer_id
    WHERE t.ticket_date >= '2026-04-01' AND t.ticket_date < '2026-07-01'
    GROUP BY c.country, t.issue_subcategory
),
ranked AS (
    SELECT q.*,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY tickets DESC, issue_subcategory) AS rn
    FROM q
)
SELECT country, rn AS position, issue_subcategory, tickets, avg_resolution_hours, avg_csat
FROM ranked
WHERE rn <= 5
ORDER BY country, rn;


-- ===== Q33: Win-back candidates: churned customers in the top CLV quartile =====
-- CLV = successful payments up to the churn date. Quartile among churned customers only (1 = highest CLV).
-- "Last known engagement" = activity in the 90 days before churn: sessions, minutes, last viewing date, and a
-- High / Medium / Low tier from NTILE(3) over watch minutes (0 minutes = 'No activity').
WITH churned AS (
    SELECT c.customer_id, cl.churn_date, cl.churn_reason
    FROM customers c
    JOIN churn_labels cl ON cl.customer_id = c.customer_id
    WHERE cl.churned = 1
),
clv AS (
    SELECT ch.customer_id, COALESCE(SUM(p.amount), 0) AS clv_before_churn
    FROM churned ch
    LEFT JOIN payments p
           ON p.customer_id = ch.customer_id
          AND p.payment_status = 'Success'
          AND p.payment_date <= ch.churn_date
    GROUP BY ch.customer_id
),
engagement AS (
    SELECT ch.customer_id,
           MAX(v.viewing_date)                      AS last_viewing_date,
           COUNT(v.viewing_id)                      AS sessions_90d,
           COALESCE(SUM(v.watch_duration_minutes), 0) AS minutes_90d
    FROM churned ch
    LEFT JOIN viewing_activity v
           ON v.customer_id = ch.customer_id
          AND v.viewing_date <= ch.churn_date
          AND v.viewing_date >  DATE_SUB(ch.churn_date, INTERVAL 90 DAY)
    GROUP BY ch.customer_id
),
scored AS (
    SELECT ch.customer_id, ch.churn_date, ch.churn_reason,
           clv.clv_before_churn,
           NTILE(4) OVER (ORDER BY clv.clv_before_churn DESC) AS clv_quartile,
           e.last_viewing_date, e.sessions_90d, e.minutes_90d,
           NTILE(3) OVER (ORDER BY e.minutes_90d DESC)        AS minutes_tier
    FROM churned ch
    JOIN clv         ON clv.customer_id = ch.customer_id
    JOIN engagement e ON e.customer_id  = ch.customer_id
)
SELECT customer_id,
       churn_date,
       churn_reason,
       ROUND(clv_before_churn, 2) AS clv_before_churn,
       last_viewing_date,
       sessions_90d,
       minutes_90d,
       CASE WHEN minutes_90d = 0 THEN 'No activity'
            WHEN minutes_tier = 1 THEN 'High'
            WHEN minutes_tier = 2 THEN 'Medium'
            ELSE 'Low' END       AS last_known_engagement
FROM scored
WHERE clv_quartile = 1
ORDER BY clv_before_churn DESC, customer_id;


-- ===== Q34: Plan-migration analysis =====
-- Every customer with 2 subscription rows made one move. Direction is judged by list price:
-- Upgrade = price goes up, Downgrade = price goes down, Same plan = re-subscription to the same plan.
-- DATA NOTE: 305 of the 875 moves are Same-plan, which are not true migrations, so they are labelled separately.
WITH ordered AS (
    SELECT s.customer_id, s.plan_id, sp.plan_name, sp.monthly_price AS list_price,
           LAG(s.plan_id)         OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_plan_id,
           LAG(sp.plan_name)      OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_plan_name,
           LAG(sp.monthly_price)  OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_price
    FROM subscriptions s
    JOIN subscription_plans sp ON sp.plan_id = s.plan_id
),
moves AS (
    SELECT customer_id,
           prev_plan_name AS from_plan,
           plan_name      AS to_plan,
           CASE WHEN list_price > prev_price THEN 'Upgrade'
                WHEN list_price < prev_price THEN 'Downgrade'
                ELSE 'Same plan' END AS direction
    FROM ordered
    WHERE prev_plan_id IS NOT NULL
)
SELECT RANK() OVER (ORDER BY COUNT(*) DESC)  AS path_rank,
       CONCAT(m.from_plan, ' -> ', m.to_plan) AS migration_path,
       m.direction,
       COUNT(*)                               AS customers,
       SUM(cl.churned)                        AS churned,
       ROUND(100 * AVG(cl.churned), 2)        AS churn_rate_pct
FROM moves m
JOIN churn_labels cl ON cl.customer_id = m.customer_id
GROUP BY m.from_plan, m.to_plan, m.direction
ORDER BY path_rank, migration_path;

-- ===== Q34b: Do upgraders churn differently from downgraders? (baseline = customers who never moved) =====
WITH ordered AS (
    SELECT s.customer_id,
           sp.monthly_price AS list_price,
           LAG(sp.monthly_price) OVER (PARTITION BY s.customer_id ORDER BY s.subscription_start_date) AS prev_price
    FROM subscriptions s
    JOIN subscription_plans sp ON sp.plan_id = s.plan_id
),
moves AS (
    SELECT customer_id,
           CASE WHEN list_price > prev_price THEN 'Upgrade'
                WHEN list_price < prev_price THEN 'Downgrade'
                ELSE 'Same plan' END AS direction
    FROM ordered
    WHERE prev_price IS NOT NULL
)
SELECT m.direction,
       COUNT(*)                        AS customers,
       SUM(cl.churned)                 AS churned,
       ROUND(100 * AVG(cl.churned), 2) AS churn_rate_pct
FROM moves m
JOIN churn_labels cl ON cl.customer_id = m.customer_id
GROUP BY m.direction
UNION ALL
SELECT 'No plan change (baseline)',
       COUNT(*),
       SUM(cl.churned),
       ROUND(100 * AVG(cl.churned), 2)
FROM churn_labels cl
WHERE cl.customer_id NOT IN (SELECT customer_id FROM subscriptions GROUP BY customer_id HAVING COUNT(*) > 1);


-- ===== Q35: WAU / MAU trend and stickiness (last 6 months) =====
-- window: 2026-01-01 .. 2026-06-30. Weeks run Monday-Sunday. Only FULL weeks are used, and a week belongs to the
-- month in which it starts. Monthly WAU = average weekly active users of the weeks in that month.
-- stickiness = avg WAU / MAU.
WITH weekly AS (
    SELECT DATE_SUB(viewing_date, INTERVAL WEEKDAY(viewing_date) DAY) AS week_start,
           COUNT(DISTINCT customer_id)                                 AS wau
    FROM viewing_activity
    WHERE viewing_date BETWEEN '2026-01-01' AND '2026-06-30'
    GROUP BY DATE_SUB(viewing_date, INTERVAL WEEKDAY(viewing_date) DAY)
),
full_weeks AS (
    SELECT week_start, wau
    FROM weekly
    WHERE week_start >= '2026-01-01'
      AND DATE_ADD(week_start, INTERVAL 6 DAY) <= '2026-06-30'
),
wau_month AS (
    SELECT DATE_FORMAT(week_start, '%Y-%m') AS ym, ROUND(AVG(wau), 0) AS avg_wau, COUNT(*) AS weeks_counted
    FROM full_weeks
    GROUP BY DATE_FORMAT(week_start, '%Y-%m')
),
mau AS (
    SELECT DATE_FORMAT(viewing_date, '%Y-%m') AS ym, COUNT(DISTINCT customer_id) AS mau
    FROM viewing_activity
    WHERE viewing_date BETWEEN '2026-01-01' AND '2026-06-30'
    GROUP BY DATE_FORMAT(viewing_date, '%Y-%m')
)
SELECT m.ym AS activity_month,
       m.mau,
       w.avg_wau,
       w.weeks_counted,
       ROUND(w.avg_wau / m.mau, 3) AS stickiness_wau_mau
FROM mau m
JOIN wau_month w ON w.ym = m.ym
ORDER BY m.ym;

-- ===== Q35b: Weekly WAU trend (full weeks only) =====
SELECT DATE_SUB(viewing_date, INTERVAL WEEKDAY(viewing_date) DAY) AS week_start,
       COUNT(DISTINCT customer_id)                                 AS wau
FROM viewing_activity
WHERE viewing_date BETWEEN '2026-01-05' AND '2026-06-28'
GROUP BY DATE_SUB(viewing_date, INTERVAL WEEKDAY(viewing_date) DAY)
ORDER BY week_start;


-- ===== Q36: Proactive retention outreach list =====
-- Active customers with NEGATIVE feedback (cleaned sentiment) within +/-14 days of
--   (a) a failed payment, or (b) a support ticket with CSAT <= 2.
-- One row per customer. Churned customers are excluded because outreach only makes sense for current subscribers.
WITH events AS (
    SELECT customer_id, payment_date AS event_date, 'Failed payment' AS trigger_type
    FROM payments
    WHERE payment_status = 'Failed'
    UNION ALL
    SELECT customer_id, ticket_date, 'Low-CSAT ticket (<=2)'
    FROM support_tickets
    WHERE customer_satisfaction_score <= 2 AND ticket_date IS NOT NULL
),
neg AS (
    SELECT customer_id, feedback_id, feedback_date, rating
    FROM customer_feedback
    WHERE sentiment_label = 'Negative'
)
SELECT n.customer_id,
       COUNT(DISTINCT n.feedback_id)                                       AS negative_feedbacks,
       GROUP_CONCAT(DISTINCT e.trigger_type ORDER BY e.trigger_type SEPARATOR ' + ') AS triggers,
       MIN(ABS(DATEDIFF(n.feedback_date, e.event_date)))                   AS min_days_apart,
       MAX(n.feedback_date)                                                AS latest_negative_feedback
FROM neg n
JOIN events e
  ON e.customer_id = n.customer_id
 AND ABS(DATEDIFF(n.feedback_date, e.event_date)) <= 14
JOIN churn_labels cl
  ON cl.customer_id = n.customer_id AND cl.churned = 0
GROUP BY n.customer_id
ORDER BY negative_feedbacks DESC, latest_negative_feedback DESC, n.customer_id;


-- ===== Q37: Customer health score (0-100) for all ACTIVE customers, ranked by risk =====
-- Five signals, each normalised to a 0 (healthy) .. 1 (risky) risk value, then weighted:
--   recency of last viewing (30%): days since last session / 365 (no viewing in the 12-month log = 365)
--   payment failure rate    (25%): failed / all payments, min-max scaled
--   support satisfaction    (20%): (5 - avg CSAT) / 4, customers with no scored ticket get the average risk
--   tenure                  (15%): shorter tenure = riskier, min-max scaled and inverted
--   current plan            (10%): the plan's observed churn rate, min-max scaled
-- risk_score_0_100 = 100 x weighted sum;  health_score_0_100 = 100 - risk_score_0_100
WITH current_sub AS (
    SELECT s.customer_id, s.plan_id,
           ROW_NUMBER() OVER (PARTITION BY s.customer_id
                              ORDER BY s.subscription_start_date DESC, s.subscription_id DESC) AS rn
    FROM subscriptions s
),
cur_plan AS (
    SELECT customer_id, plan_id FROM current_sub WHERE rn = 1
),
plan_churn AS (
    SELECT cp.plan_id, AVG(cl.churned) AS plan_churn_rate
    FROM cur_plan cp
    JOIN churn_labels cl ON cl.customer_id = cp.customer_id
    GROUP BY cp.plan_id
),
active AS (
    SELECT c.customer_id, c.registration_date
    FROM customers c JOIN churn_labels cl ON cl.customer_id = c.customer_id
    WHERE cl.churned = 0
),
last_view AS (
    SELECT customer_id, MAX(viewing_date) AS last_view_date FROM viewing_activity GROUP BY customer_id
),
pay AS (
    SELECT customer_id, COUNT(*) AS payments, SUM(payment_status = 'Failed') AS failed_payments
    FROM payments GROUP BY customer_id
),
csat AS (
    SELECT customer_id, AVG(customer_satisfaction_score) AS avg_csat
    FROM support_tickets
    WHERE customer_satisfaction_score IS NOT NULL
    GROUP BY customer_id
),
metrics AS (
    SELECT a.customer_id,
           sp.plan_name,
           DATEDIFF('2026-06-30', a.registration_date)                              AS tenure_days,
           LEAST(COALESCE(DATEDIFF('2026-06-30', lv.last_view_date), 365), 365)     AS days_since_last_view,
           COALESCE(p.failed_payments / NULLIF(p.payments, 0), 0)                   AS failed_payment_rate,
           cs.avg_csat,
           pc.plan_churn_rate
    FROM active a
    JOIN cur_plan cp           ON cp.customer_id = a.customer_id
    JOIN subscription_plans sp ON sp.plan_id     = cp.plan_id
    JOIN plan_churn pc         ON pc.plan_id     = cp.plan_id
    LEFT JOIN last_view lv     ON lv.customer_id = a.customer_id
    LEFT JOIN pay p            ON p.customer_id  = a.customer_id
    LEFT JOIN csat cs          ON cs.customer_id = a.customer_id
),
bounds AS (
    SELECT MIN(failed_payment_rate) AS min_f, MAX(failed_payment_rate) AS max_f,
           MIN(tenure_days)         AS min_t, MAX(tenure_days)         AS max_t,
           MIN(plan_churn_rate)     AS min_p, MAX(plan_churn_rate)     AS max_p,
           AVG((5 - avg_csat) / 4)  AS avg_csat_risk
    FROM metrics
),
norm AS (
    SELECT m.*,
           m.days_since_last_view / 365 AS recency_risk,
           COALESCE((m.failed_payment_rate - b.min_f) / NULLIF(b.max_f - b.min_f, 0), 0) AS payment_risk,
           COALESCE((5 - m.avg_csat) / 4, b.avg_csat_risk)                               AS csat_risk,
           1 - COALESCE((m.tenure_days - b.min_t) / NULLIF(b.max_t - b.min_t, 0), 0)     AS tenure_risk,
           COALESCE((m.plan_churn_rate - b.min_p) / NULLIF(b.max_p - b.min_p, 0), 0)     AS plan_risk
    FROM metrics m
    CROSS JOIN bounds b
),
scored AS (
    SELECT norm.*,
           100 * (0.30 * recency_risk + 0.25 * payment_risk + 0.20 * csat_risk
                  + 0.15 * tenure_risk + 0.10 * plan_risk) AS risk_score
    FROM norm
)
SELECT RANK() OVER (ORDER BY risk_score DESC) AS risk_rank,
       customer_id,
       plan_name                       AS current_plan,
       days_since_last_view,
       ROUND(failed_payment_rate, 3)   AS failed_payment_rate,
       ROUND(avg_csat, 2)              AS avg_csat,
       tenure_days,
       ROUND(risk_score, 1)            AS risk_score_0_100,
       ROUND(100 - risk_score, 1)      AS health_score_0_100
FROM scored
ORDER BY risk_rank, customer_id;
