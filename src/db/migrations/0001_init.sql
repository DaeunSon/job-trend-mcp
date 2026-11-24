CREATE TABLE postings (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_name          text NOT NULL,
  source_job_id        text NOT NULL,
  doc_id               text,
  title                text NOT NULL DEFAULT '',
  normalized_title     text NOT NULL DEFAULT '',
  company_name         text,
  company_key          text NOT NULL DEFAULT '',
  job_function_name    text NOT NULL DEFAULT '',
  job_category_name    text NOT NULL DEFAULT '',
  employment_type_name text NOT NULL DEFAULT '',
  employment_type_norm text NOT NULL DEFAULT '',
  work_arrangement     text,
  city_name            text,
  location_blob        text NOT NULL DEFAULT '',
  salary_min           numeric,
  salary_max           numeric,
  currency_code        text,
  pay_period           text,
  crawl_status         text NOT NULL DEFAULT 'ACTIVE',
  posted_on            date,
  sort_key             text NOT NULL DEFAULT '',
  recrawl_key          text NOT NULL DEFAULT '',
  first_collected_at   timestamptz,
  last_seen_at         timestamptz,
  ingest_source        text NOT NULL,
  doc                  jsonb NOT NULL,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_name, source_job_id)
);
CREATE INDEX postings_function_idx ON postings (job_function_name);
CREATE INDEX postings_category_idx ON postings (job_category_name);
CREATE INDEX postings_company_idx  ON postings (company_key);
CREATE INDEX postings_sort_idx     ON postings (sort_key DESC, id);

CREATE TABLE posting_skills (
  posting_id     bigint NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
  canonical_name text NOT NULL,
  PRIMARY KEY (posting_id, canonical_name)
);
CREATE INDEX posting_skills_name_idx ON posting_skills (canonical_name);

CREATE TABLE posting_observations (
  posting_id    bigint NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
  observed_on   date NOT NULL,
  ingest_source text NOT NULL,
  PRIMARY KEY (posting_id, observed_on)
);
CREATE INDEX posting_observations_date_idx ON posting_observations (observed_on);
