-- ==============================================================================
-- Jan Niti AI - Database Schema Migration: Stage 2A
-- File: migrations/001_add_academic_stage_columns.sql
-- Description:
-- Extends the Supabase 'applications' table to support direct persistence of
-- stage-aware academic columns while preserving 100% backward compatibility.
-- Note: In the current Supabase PostgREST client runtime, full stage metadata
-- is already immutably preserved in 'audit_logs' (action='APPLICATION_CREATED').
-- Executing this script in the Supabase SQL Editor adds direct columns as well.
-- ==============================================================================

DO $$
BEGIN
    -- 1. Academic Stage (Controlled enum or varchar check)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'academic_stage'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN academic_stage VARCHAR(30) DEFAULT 'LEGACY_UNSPECIFIED';

        ALTER TABLE public.applications
        ADD CONSTRAINT chk_applications_academic_stage
        CHECK (academic_stage IN (
            'FIRST_YEAR',
            'SECOND_YEAR',
            'THIRD_YEAR',
            'FOURTH_YEAR',
            'POSTGRADUATE',
            'LEGACY_UNSPECIFIED'
        ));
    END IF;

    -- 2. Qualification Type (Only applicable for FIRST_YEAR)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'qualification_type'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN qualification_type VARCHAR(30) NULL;

        ALTER TABLE public.applications
        ADD CONSTRAINT chk_applications_qualification_type
        CHECK (qualification_type IS NULL OR qualification_type IN ('HSC_12TH', 'DIPLOMA', 'OTHER'));
    END IF;

    -- 3. Stage-specific score columns
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'qualifying_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN qualifying_score NUMERIC(5, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'ssc_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN ssc_score NUMERIC(5, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'first_year_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN first_year_score NUMERIC(5, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'second_year_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN second_year_score NUMERIC(5, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'third_year_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN third_year_score NUMERIC(5, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'applications'
          AND column_name = 'ug_score'
    ) THEN
        ALTER TABLE public.applications
        ADD COLUMN ug_score NUMERIC(5, 2) NULL;
    END IF;

END $$;
