-- Preferences and reflection records belong to the single-owner application schema.
CREATE TABLE app.daily_routine_settings (
 id integer PRIMARY KEY CHECK(id=1), enabled boolean NOT NULL DEFAULT false,
 wake_time time, midday_time time, evening_time time, weekly_day integer NOT NULL DEFAULT 5 CHECK(weekly_day BETWEEN 0 AND 6),
 rest_day integer NOT NULL DEFAULT 6 CHECK(rest_day BETWEEN 0 AND 6),
 city text NOT NULL DEFAULT '', latitude double precision, longitude double precision,
 approved_feeds text[] NOT NULL DEFAULT '{}', open_channel boolean NOT NULL DEFAULT false,
 low_energy integer NOT NULL DEFAULT 2 CHECK(low_energy BETWEEN 1 AND 5),
 low_days integer NOT NULL DEFAULT 3 CHECK(low_days BETWEEN 1 AND 5),
 skipped_days integer NOT NULL DEFAULT 5 CHECK(skipped_days BETWEEN 1 AND 30),
 enabled_since date, version integer NOT NULL DEFAULT 1
);
INSERT INTO app.daily_routine_settings(id) VALUES(1);
CREATE TABLE app.routine_checkins (
 day date NOT NULL, anchor text NOT NULL CHECK(anchor IN ('morning','midday','evening')),
 energy integer NOT NULL CHECK(energy BETWEEN 1 AND 5), PRIMARY KEY(day,anchor)
);
CREATE TABLE app.routine_predictions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), domain text NOT NULL, claim text NOT NULL,
 gut_note text NOT NULL, kind text NOT NULL CHECK(kind IN ('binary','duration','quantity')),
 probability numeric CHECK(probability BETWEEN 0 AND 1), estimate numeric, due_date date NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz, result boolean, actual numeric,
 CHECK((kind='binary' AND probability IS NOT NULL AND estimate IS NULL) OR
       (kind<>'binary' AND estimate IS NOT NULL AND probability IS NULL))
);
CREATE TABLE app.routine_pool (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL CHECK(kind IN ('spark','wildcard','opportunity')),
 title text NOT NULL, source_url text NOT NULL DEFAULT '', relevance text NOT NULL DEFAULT '',
 active boolean NOT NULL DEFAULT true
);
CREATE TABLE app.routine_editions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL, period text NOT NULL,
 for_date date NOT NULL, content jsonb NOT NULL, feedback text CHECK(feedback IN ('kept','dropped')),
 feedback_note text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(kind,period)
);
CREATE INDEX routine_editions_day ON app.routine_editions(for_date,kind);
CREATE TABLE app.routine_hypotheses (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), pattern text NOT NULL, week date NOT NULL UNIQUE,
 evidence uuid[] NOT NULL, counterexamples uuid[] NOT NULL, state text NOT NULL DEFAULT 'proposed'
 CHECK(state IN ('proposed','confirmed','rejected','unsure'))
);
