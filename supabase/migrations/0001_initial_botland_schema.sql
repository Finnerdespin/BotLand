-- BotLand initial schema (Postgres / Supabase)
-- Project: botland (ppdgzhzmtgzhccxlgefr)

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS locations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS houses (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  name TEXT NOT NULL,
  location_id TEXT NOT NULL,
  rooms JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE TABLE IF NOT EXISTS bots (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  avatar TEXT NOT NULL DEFAULT 'default',
  personality TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
  provider TEXT NOT NULL DEFAULT 'openai',
  capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
  permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
  house_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'idle',
  activity TEXT NOT NULL DEFAULT 'relaxing',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT bots_name_unique UNIQUE (name)
);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT 'Conversation',
  participants JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_type TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS letters (
  id TEXT PRIMARY KEY,
  sender_bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  read_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS activities (
  id TEXT PRIMARY KEY,
  bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  description TEXT NOT NULL,
  location_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS relationships (
  id TEXT PRIMARY KEY,
  bot_a TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  bot_b TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  score INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (bot_a, bot_b)
);
CREATE TABLE IF NOT EXISTS world_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_letters_created ON letters(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_letters_sender ON letters(sender_bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_bot ON memories(bot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activities_bot ON activities(bot_id, created_at DESC);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE houses ENABLE ROW LEVEL SECURITY;
ALTER TABLE bots ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE letters ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE world_state ENABLE ROW LEVEL SECURITY;

-- Seed world locations and the human player's house
INSERT INTO locations (id, name, kind, x, y, description) VALUES
  ('village_square','Village Square','village_square',10,10,'The heart of BotLand.'),
  ('park','Park','park',6,6,'A sunny park.'),
  ('forest','Forest','forest',2,14,'Quiet pine forest.'),
  ('lake','Lake','lake',16,14,'Calm lake.'),
  ('cafe','Cafe','cafe',12,6,'Warm drinks.'),
  ('library','Library','library',8,14,'Reading nook.'),
  ('player_house','Your House','player_house',14,10,'Your cozy home.')
ON CONFLICT (id) DO NOTHING;

INSERT INTO houses (id, owner_id, name, location_id, rooms) VALUES
  ('house_player','player','Your House','player_house','["living","desk","bed","bookshelf","fireplace"]'::jsonb)
ON CONFLICT (id) DO NOTHING;

INSERT INTO world_state (key, value) VALUES
  ('time', now()::text),
  ('season','spring'),
  ('weather','sunny')
ON CONFLICT (key) DO NOTHING;
