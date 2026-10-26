-- C2 - Requêtes SQL documentées (PostgreSQL).
-- Chaque requête : objectif, jointures, filtres justifiés. Exécuter avec :
--   docker compose exec db psql -U airdata -d airdata -f /sql/queries.sql

-- Q1. Moyenne PM2.5 et NO2 par commune sur les 7 derniers jours
-- Jointure commune -> mesure (1-N) pour récupérer le nom ; filtre temporel = fenêtre de suivi métier.
SELECT c.code_insee, c.nom,
       ROUND(AVG(m.pm25)::numeric, 2) AS pm25_moy,
       ROUND(AVG(m.no2)::numeric, 2)  AS no2_moy,
       COUNT(*)                       AS nb_mesures
FROM commune c
JOIN mesure m ON m.code_insee = c.code_insee
WHERE m.horodatage >= NOW() - INTERVAL '7 days'
GROUP BY c.code_insee, c.nom
ORDER BY pm25_moy DESC;

-- Q2. Top 10 des pics horaires de PM2.5 (dépassement du seuil OMS journalier 15 µg/m³ à titre indicatif)
SELECT c.nom, m.horodatage, m.pm25
FROM mesure m
JOIN commune c USING (code_insee)
WHERE m.pm25 > 15
ORDER BY m.pm25 DESC
LIMIT 10;

-- Q3. Moyenne glissante PM2.5 sur 24 h par commune (fonction de fenêtre)
SELECT code_insee, horodatage, pm25,
       ROUND(AVG(pm25) OVER (
           PARTITION BY code_insee ORDER BY horodatage
           ROWS BETWEEN 23 PRECEDING AND CURRENT ROW)::numeric, 2) AS pm25_glissant_24h
FROM mesure
WHERE code_insee = '75056';

-- Q4. Nombre d'heures de dépassement par commune et par jour
SELECT code_insee, DATE(horodatage) AS jour,
       COUNT(*) FILTER (WHERE pm25 > 15) AS heures_depassement
FROM mesure
GROUP BY code_insee, DATE(horodatage)
HAVING COUNT(*) FILTER (WHERE pm25 > 15) > 0
ORDER BY jour DESC, heures_depassement DESC;

-- Q5. Communes suivies par des abonnés consentants (jointure 3 tables, sans exposer les emails)
SELECT c.nom, COUNT(a.id) AS nb_abonnes
FROM abonne a
JOIN commune c ON c.code_insee = a.code_insee
WHERE a.consentement IS TRUE
GROUP BY c.nom
ORDER BY nb_abonnes DESC;

-- Q6. Optimisation : mesurer l'effet d'un index composite sur la requête la plus fréquente de l'API
EXPLAIN ANALYZE SELECT * FROM mesure WHERE code_insee = '75056' AND horodatage >= NOW() - INTERVAL '7 days';
CREATE INDEX IF NOT EXISTS ix_mesure_commune_heure ON mesure (code_insee, horodatage);
EXPLAIN ANALYZE SELECT * FROM mesure WHERE code_insee = '75056' AND horodatage >= NOW() - INTERVAL '7 days';
-- Preuve : capturer les deux plans (Seq Scan -> Index Scan) et les temps d'exécution.
