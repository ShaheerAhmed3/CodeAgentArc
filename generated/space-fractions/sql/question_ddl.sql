CREATE TABLE questions (
  id UUID PRIMARY KEY,
  prompt TEXT NOT NULL,
  options TEXT[] NOT NULL,
  answer_index INTEGER NOT NULL
);
