-- Jeu de test RGPD : abonnés FICTIFS (domaine example.org réservé aux exemples, n'appartient à personne).
-- Sert à démontrer Q5 (comptage des seuls abonnés consentants) et la purge RGPD (src/db/purge_rgpd.py).
-- Exécuter : docker compose exec db psql -U airdata -d airdata -f /sql/seed_abonnes_test.sql
DELETE FROM abonne WHERE email LIKE '%@example.org';
INSERT INTO abonne (email, code_insee, consentement, date_consentement, derniere_activite) VALUES
 ('test1@example.org', '75056', true,  now(), now()),
 ('test2@example.org', '75056', true,  now(), now()),
 ('test3@example.org', '92012', true,  now(), now()),
 ('test4@example.org', '93048', false, NULL,  now()),                                          -- sans consentement -> purgé
 ('test5@example.org', '92012', true,  now() - interval '30 months', now() - interval '30 months'); -- inactif > 24 mois -> purgé