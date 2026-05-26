WITH paper_contacted AS (
    SELECT
        pstr.person_id,
        pstr.first_marketing_activity_fiscal_year AS first_papersent_fiscal_year,
        pstr.first_marketing_activity_dt AS first_papersent_dt,
        str.product,
        str.sub_product
    FROM PDP_UG_ANALYTICS.person_streams pstr
    INNER JOIN PDP_UG_ANALYTICS.streams str
        ON pstr.stream_key = str.stream_key
    INNER JOIN PDP_UG_ANALYTICS.marketing_activity ma
        ON ma.marketing_activity_key = pstr.first_marketing_activity_key
    WHERE str.product = 'Cultivate'
      AND str.sub_product = 'Inquiry Generation'
      AND ARRAY_CONTAINS('paper'::VARIANT, str.channel_list)
      --AND pstr.first_marketing_activity_fiscal_year >= 2024
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY pstr.person_id
        ORDER BY pstr.first_marketing_activity_dt, str.product, str.sub_product
    ) = 1
),
contacted AS (
    SELECT
        pstr.person_id,
        pstr.first_marketing_activity_fiscal_year AS first_contact_fiscal_year,
        psp.audience,
        pstr.first_engagement_activity_dt,
        pstr.first_marketing_activity_dt,
        str.sub_product AS marketing_sub_product,
        str.product AS marketing_product,
        str.channel_list,
        CASE
            WHEN MONTH(pstr.first_engagement_activity_dt) > 6 THEN YEAR(pstr.first_engagement_activity_dt) + 1
            ELSE YEAR(pstr.first_engagement_activity_dt)
        END AS engaged_fiscal_year
    FROM PDP_UG_ANALYTICS.person_streams pstr
    INNER JOIN PDP_UG_ANALYTICS.streams str
        ON pstr.stream_key = str.stream_key
    INNER JOIN PDP_UG_ANALYTICS.marketing_activity ma
        ON ma.marketing_activity_key = pstr.first_marketing_activity_key
    LEFT JOIN (
        SELECT
            person_id AS person_2,
            audience,
            product,
            sub_product
        FROM person_sub_products
        WHERE product = 'Apply'
          AND sub_product = 'Application Generation'
    ) psp
        ON psp.person_2 = pstr.person_id
        AND psp.product = str.product
        AND psp.sub_product = str.sub_product
    WHERE ARRAY_CONTAINS('email'::VARIANT, str.channel_list)
      AND str.product = 'Cultivate'
      AND str.sub_product = 'Inquiry Generation'
      AND (ma.event_name NOT ILIKE '%parent%' OR ma.event_name IS NULL)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY pstr.person_id
        ORDER BY pstr.first_marketing_activity_dt, str.product, str.sub_product
    ) = 1
),
gs as 
(
SELECT
    COUNT(a.person_id) AS marketing_contacts,
    COUNT(a.first_engagement_activity_dt) AS engaged_contacts,
    a.first_contact_fiscal_year,
    b.first_papersent_fiscal_year ,
    a.engaged_fiscal_year,
    a.audience,
    a.marketing_sub_product,
    a.marketing_product,
    DATEDIFF(day, DATE(a.first_marketing_activity_dt), DATE(b.first_papersent_dt)) AS date_diff_marketing_paper,
    DATEDIFF(day, DATE(b.first_papersent_dt), DATE(a.first_engagement_activity_dt)) AS date_diff_paper_engaged
FROM contacted a
LEFT JOIN paper_contacted b
    ON a.person_id = b.person_id
    AND a.marketing_product = b.product
    AND a.marketing_sub_product = b.sub_product
GROUP BY
    a.first_contact_fiscal_year,
    b.first_papersent_fiscal_year ,
    a.engaged_fiscal_year,
    a.audience,
    a.marketing_sub_product,
    a.marketing_product,
    date_diff_marketing_paper,
    date_diff_paper_engaged;
