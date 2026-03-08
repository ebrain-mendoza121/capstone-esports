-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "alembic_version" (
    "version_num" VARCHAR(32) NOT NULL,

    CONSTRAINT "alembic_version_pkc" PRIMARY KEY ("version_num")
);

-- CreateTable
CREATE TABLE "derived_metrics" (
    "id" SERIAL NOT NULL,
    "match_id" VARCHAR NOT NULL,
    "puuid" VARCHAR NOT NULL,
    "kda" DOUBLE PRECISION,
    "cs_per_min" DOUBLE PRECISION,
    "gold_per_min" DOUBLE PRECISION,
    "kill_participation" DOUBLE PRECISION,
    "damage_share" DOUBLE PRECISION,
    "vision_per_min" DOUBLE PRECISION,

    CONSTRAINT "derived_metrics_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "matches" (
    "match_id" VARCHAR(64) NOT NULL,
    "game_creation" BIGINT NOT NULL,
    "game_duration" INTEGER NOT NULL,
    "queue_id" INTEGER NOT NULL,
    "patch_version" VARCHAR(32),
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "matches_pkey" PRIMARY KEY ("match_id")
);

-- CreateTable
CREATE TABLE "participant_stats" (
    "id" SERIAL NOT NULL,
    "match_id" VARCHAR(64) NOT NULL,
    "player_id" INTEGER NOT NULL,
    "team_id" INTEGER NOT NULL,
    "champion" VARCHAR(64),
    "role" VARCHAR(32),
    "kills" INTEGER NOT NULL,
    "deaths" INTEGER NOT NULL,
    "assists" INTEGER NOT NULL,
    "gold_earned" INTEGER NOT NULL,
    "total_damage" INTEGER NOT NULL,
    "cs" INTEGER NOT NULL,
    "vision_score" INTEGER NOT NULL,
    "win" BOOLEAN,

    CONSTRAINT "participant_stats_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "players" (
    "id" SERIAL NOT NULL,
    "riot_id" VARCHAR(64) NOT NULL,
    "tag_line" VARCHAR(16) NOT NULL,
    "puuid" VARCHAR(128) NOT NULL,
    "region" VARCHAR(16) NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "players_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "team_objectives" (
    "id" SERIAL NOT NULL,
    "match_id" VARCHAR(64) NOT NULL,
    "team_id" INTEGER NOT NULL,
    "towers" INTEGER NOT NULL,
    "dragons" INTEGER NOT NULL,
    "barons" INTEGER NOT NULL,
    "win_flag" BOOLEAN NOT NULL,

    CONSTRAINT "team_objectives_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ix_derived_metrics_match_id" ON "derived_metrics"("match_id");

-- CreateIndex
CREATE INDEX "ix_derived_metrics_puuid" ON "derived_metrics"("puuid");

-- CreateIndex
CREATE UNIQUE INDEX "uq_derived_metrics_match_puuid" ON "derived_metrics"("match_id", "puuid");

-- CreateIndex
CREATE INDEX "ix_matches_game_creation" ON "matches"("game_creation");

-- CreateIndex
CREATE INDEX "ix_matches_queue_id" ON "matches"("queue_id");

-- CreateIndex
CREATE INDEX "ix_participant_stats_champion" ON "participant_stats"("champion");

-- CreateIndex
CREATE INDEX "ix_participant_stats_match_id" ON "participant_stats"("match_id");

-- CreateIndex
CREATE INDEX "ix_participant_stats_player_id" ON "participant_stats"("player_id");

-- CreateIndex
CREATE UNIQUE INDEX "ix_players_puuid" ON "players"("puuid");

-- CreateIndex
CREATE INDEX "ix_team_objectives_match_id" ON "team_objectives"("match_id");

-- AddForeignKey
ALTER TABLE "derived_metrics" ADD CONSTRAINT "derived_metrics_match_id_fkey" FOREIGN KEY ("match_id") REFERENCES "matches"("match_id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "derived_metrics" ADD CONSTRAINT "derived_metrics_puuid_fkey" FOREIGN KEY ("puuid") REFERENCES "players"("puuid") ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "participant_stats" ADD CONSTRAINT "participant_stats_match_id_fkey" FOREIGN KEY ("match_id") REFERENCES "matches"("match_id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "participant_stats" ADD CONSTRAINT "participant_stats_player_id_fkey" FOREIGN KEY ("player_id") REFERENCES "players"("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- AddForeignKey
ALTER TABLE "team_objectives" ADD CONSTRAINT "team_objectives_match_id_fkey" FOREIGN KEY ("match_id") REFERENCES "matches"("match_id") ON DELETE CASCADE ON UPDATE NO ACTION;

