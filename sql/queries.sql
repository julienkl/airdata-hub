-- C2 - Requêtes SQL documentées (PostgreSQL).
-- Chaque requête : objectif, jointures, filtres justifiés. Exécuter avec :
--   docker compose exec db psql -U airdata -d airdata -f /sql/queries.sql

-- Q1. Moyenne PM2.5 et NO2 par commune sur les 7 derniers jours
-- INNER JOIN : une commune sans mesure n'a pas de moyenne, elle est volontairement exclue.
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

-- Q2. Top 10 des pics horaires de PM2.5, avec repérage du dépassement du seuil OMS journalier (15 µg/m³, indicatif)
SELECT c.nom, m.horodatage, m.pm25,
       m.pm25 > 15 AS au_dessus_seuil_oms
FROM mesure m
JOIN commune c USING (code_insee)
WHERE m.pm25 IS NOT NULL
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

-- Q5. Communes suivies par des abonnés consentants (jointure abonne -> commune, sans exposer les emails)
-- INNER JOIN : seules les communes qui ont au moins un abonné consentant nous intéressent.
SELECT c.nom, COUNT(a.id) AS nb_abonnes
FROM abonne a
JOIN commune c ON c.code_insee = a.code_insee
WHERE a.consentement IS TRUE
GROUP BY c.nom
ORDER BY nb_abonnes DESC;

-- Q6. Optimisation par index : requête « top des pics de PM2.5 » (Q2), appelée par le tableau de bord.
-- Constat préalable : la requête principale de l'API (commune + période) est DÉJÀ indexée :
--   ix_mesure_code_insee (créé par le modèle) et uq_mesure_commune_heure (contrainte anti-doublons,
--   PostgreSQL crée automatiquement un index pour toute contrainte d'unicité). Inutile d'en ajouter un.
-- En revanche, rien n'indexe pm25 : PostgreSQL doit lire toute la table puis trier.
ANALYZE mesure;                                   -- statistiques à jour pour le planificateur
DROP INDEX IF EXISTS ix_mesure_pm25;              -- rend la démonstration rejouable

-- AVANT : attendu « Seq Scan » + « Sort » (lecture et tri de toutes les lignes)
EXPLAIN ANALYZE
SELECT code_insee, horodatage, pm25 FROM mesure ORDER BY pm25 DESC LIMIT 10;

CREATE INDEX ix_mesure_pm25 ON mesure (pm25 DESC);
ANALYZE mesure;

-- APRÈS : attendu « Index Scan using ix_mesure_pm25 » (lecture des 10 lignes utiles seulement)
EXPLAIN ANALYZE
SELECT code_insee, horodatage, pm25 FROM mesure ORDER BY pm25 DESC LIMIT 10;
-- Preuve : capturer les deux plans et comparer « Execution Time » et le nombre de lignes lues.

-- Q7. Couverture de la collecte : communes SANS aucune mesure sur les 7 derniers jours.
-- LEFT JOIN (jointure externe) : garde TOUTES les communes, même sans mesure correspondante
-- (les colonnes de mesure valent alors NULL). Un INNER JOIN les ferait disparaître.
-- Le filtre de date est dans la condition ON, pas dans le WHERE : dans le WHERE, il éliminerait
-- les lignes NULL et transformerait le LEFT JOIN en INNER JOIN.
SELECT c.code_insee, c.nom, c.population, COUNT(m.id) AS nb_mesures_7j
FROM commune c
LEFT JOIN mesure m
       ON m.code_insee = c.code_insee
      AND m.horodatage >= NOW() - INTERVAL '7 days'
GROUP BY c.code_insee, c.nom, c.population
HAVING COUNT(m.id) = 0
ORDER BY c.population DESC;

-- Q8. RGPD : affichage pseudonymisé pour toute consultation ou capture d'écran.
-- Les mots de passe des comptes API sont HACHÉS (PBKDF2-SHA256, sel aléatoire, 200 000 itérations) :
-- personne, pas même l'administrateur, ne peut les relire.
SELECT username, role, LEFT(password_hash, 30) || '…' AS password_hash
FROM api_user;
-- Les emails ne peuvent pas être hachés (il faut pouvoir envoyer l'alerte) : ils sont masqués à l'affichage.
SELECT regexp_replace(email, '^(.).*(@.*)$', '\1***\2') AS email_masque,
       code_insee, consentement, derniere_activite
FROM abonne;
