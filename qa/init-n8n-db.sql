-- Script de inicializacao automatica da database n8n no PostgreSQL de QA
SELECT 'CREATE DATABASE n8n_qa'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n_qa')\gexec
