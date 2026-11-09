-- Separate database for the automated backend tests, so tests never touch application data.
CREATE DATABASE namaa_test;
\connect namaa_test
CREATE EXTENSION IF NOT EXISTS postgis;
