CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  options TEXT[] NOT NULL,
  answer_index INTEGER NOT NULL
);
