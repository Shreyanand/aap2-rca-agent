ALTER TABLE aap2_job_results
    ADD COLUMN IF NOT EXISTS cross_job_pattern_confidence TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'aap2_job_results_cross_job_pattern_confidence_check'
    ) THEN
        ALTER TABLE aap2_job_results
            ADD CONSTRAINT aap2_job_results_cross_job_pattern_confidence_check
            CHECK (
                cross_job_pattern_confidence IS NULL
                OR cross_job_pattern_confidence IN ('high', 'medium', 'low')
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS aap2_job_results_cross_job_pattern_idx
    ON aap2_job_results(cross_job_pattern);
