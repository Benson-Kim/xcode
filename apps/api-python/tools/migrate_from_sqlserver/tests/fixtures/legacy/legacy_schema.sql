-- The legacy application's schema (alembic d8e1a4f9c220), from pg_restore -s of its dump,
-- without owners, grants and \restrict lines. Schema only: the fixture's rows are
-- synthetic (legacy_rows.sql).

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';

CREATE TYPE public.factor_enum AS ENUM (
    'plus',
    'minus'
);

CREATE FUNCTION public.after_insert_or_update_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Case 1: update budgets for the new category/month/vehicle if the record is locked
    IF NEW.locked = true AND NEW.category_id IS NOT NULL AND NEW.vehicle_id IS NOT NULL THEN
        INSERT INTO budgets (category_id, vehicle_id, year, month, actual)
        SELECT NEW.category_id,
               NEW.vehicle_id,
               EXTRACT(YEAR FROM NEW.date),
               EXTRACT(MONTH FROM NEW.date),
               COALESCE((
                   SELECT SUM(ABS(r.amount))
                   FROM records r
                   WHERE r.category_id = NEW.category_id
                     AND r.vehicle_id   = NEW.vehicle_id
                     AND r.locked = true
                     AND EXTRACT(YEAR FROM r.date) = EXTRACT(YEAR FROM NEW.date)
                     AND EXTRACT(MONTH FROM r.date) = EXTRACT(MONTH FROM NEW.date)
               ), 0)
        ON CONFLICT (category_id, vehicle_id, year, month)
        DO UPDATE SET actual = EXCLUDED.actual;
    END IF;

-- Case 2: category or vehicle changed → recompute old category/month/vehicle if old record was locked
    IF TG_OP = 'UPDATE'
       AND OLD.locked = true
       AND (OLD.category_id IS DISTINCT FROM NEW.category_id OR OLD.vehicle_id IS DISTINCT FROM NEW.vehicle_id)
       AND OLD.category_id IS NOT NULL
       AND OLD.vehicle_id IS NOT NULL THEN

INSERT INTO budgets (category_id, vehicle_id, year, month, actual)
        SELECT OLD.category_id,
               OLD.vehicle_id,
               EXTRACT(YEAR FROM OLD.date),
               EXTRACT(MONTH FROM OLD.date),
               COALESCE((
                   SELECT SUM(ABS(r.amount))
                   FROM records r
                   WHERE r.category_id = OLD.category_id
                     AND r.vehicle_id   = OLD.vehicle_id
                     AND r.locked = true
                     AND EXTRACT(YEAR FROM r.date) = EXTRACT(YEAR FROM OLD.date)
                     AND EXTRACT(MONTH FROM r.date) = EXTRACT(MONTH FROM OLD.date)
               ), 0)
        ON CONFLICT (category_id, vehicle_id, year, month)
        DO UPDATE SET actual = EXCLUDED.actual;
    END IF;

RETURN NEW;
END;
$$;

CREATE FUNCTION public.after_insert_update_petty_cash() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    affected_date DATE;
    opening NUMERIC := 0;
    total_plus NUMERIC := 0;
    total_minus NUMERIC := 0;
    closing NUMERIC := 0;
    old_closing NUMERIC := 0;
    delta NUMERIC := 0;
BEGIN
    -- Insert into records table only if newly committed
    IF TG_OP != 'DELETE' AND NEW.committed = true AND NEW.minus IS NOT NULL  AND NEW.entry_id IS NOT NULL AND NEW.vehicle_id IS NOT NULL THEN
        INSERT INTO records (petty_cash_id, entry_id, vehicle_id, quantity, amount, date, locked)
        VALUES (NEW.id, NEW.entry_id, NEW.vehicle_id, NEW.quantity, NEW.minus, NEW.date, true)
        ON CONFLICT (petty_cash_id)
        DO UPDATE SET entry_id  = EXCLUDED.entry_id,
                  vehicle_id = EXCLUDED.vehicle_id,
                  quantity   = EXCLUDED.quantity,
                  amount     = EXCLUDED.amount,
                  date       = EXCLUDED.date,
                  locked     = EXCLUDED.locked;
    END IF;

-- LOGIC ON UPDATING DAILY BALANCES
    IF (
        TG_OP = 'INSERT'
        OR TG_OP = 'DELETE'
        OR (TG_OP = 'UPDATE' AND (
            NEW.plus IS DISTINCT FROM OLD.plus OR NEW.minus IS DISTINCT FROM OLD.minus
        ))
    ) THEN
        affected_date := COALESCE(NEW.date, OLD.date);

-- FIXED: Calculate opening balance from ALL previous transactions
        -- This eliminates race conditions with daily_balances table
        SELECT COALESCE(SUM(plus) - SUM(minus), 0) INTO opening
        FROM petty_cash
        WHERE date < affected_date;

-- Sum all transactions for the affected date (no committed filter)
        SELECT 
            COALESCE(SUM(plus), 0),
            COALESCE(SUM(minus), 0)
        INTO total_plus, total_minus
        FROM petty_cash
        WHERE date = affected_date;

-- Compute new closing balance
        closing := opening + total_plus - total_minus;

-- Get previously stored closing (if exists)
        SELECT closing_balance INTO old_closing
        FROM petty_cash_daily_balances
        WHERE date = affected_date;

-- Compute delta
        delta := closing - COALESCE(old_closing, 0);

-- Upsert daily balance
        INSERT INTO petty_cash_daily_balances(date, opening_balance, closing_balance, updated_at)
        VALUES (affected_date, opening, closing, NOW())
        ON CONFLICT (date) DO UPDATE
        SET opening_balance = EXCLUDED.opening_balance,
            closing_balance = EXCLUDED.closing_balance,
            updated_at = NOW();

-- Apply delta to all future days
        IF delta <> 0 THEN
            UPDATE petty_cash_daily_balances
            SET 
                opening_balance = opening_balance + delta,
                closing_balance = closing_balance + delta,
                updated_at = NOW()
            WHERE date > affected_date;
        END IF;
    END IF;

RETURN NEW;
END;
$$;

CREATE FUNCTION public.after_update_category() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.title <> OLD.title THEN
        UPDATE budgets SET category = NEW.title WHERE category_id = NEW.id;
    END IF;
    IF NEW.factor IS DISTINCT FROM OLD.factor THEN
        UPDATE budgets SET factor = NEW.factor WHERE category_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.after_update_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    
    UPDATE records SET name = NEW.title, category_id = NEW.category_id WHERE entry_id = NEW.id;
    UPDATE petty_cash SET name = NEW.title WHERE entry_id = NEW.id;
    
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.after_update_role_trigger_function() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE users
    SET permissions = COALESCE((SELECT array_agg(p.title) FROM permissions p WHERE p.id = ANY(NEW.permissions)), '{}')
    WHERE role_id = NEW.id;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.after_update_vehicle() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.registration <> OLD.registration THEN
        UPDATE records SET registration = NEW.registration WHERE vehicle_id = NEW.id;
        UPDATE petty_cash SET registration = NEW.registration WHERE vehicle_id = NEW.id;
        UPDATE provisions SET registration = NEW.registration WHERE vehicle_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.before_delete_record() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF OLD.locked THEN
        RAISE EXCEPTION 'Cannot delete a record that is already locked';
    END IF;
    RETURN OLD;
END;
$$;

CREATE FUNCTION public.before_insert_or_update_budget() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    cat RECORD;
BEGIN
    SELECT title, factor INTO cat FROM categories WHERE id = NEW.category_id;
    NEW.category = cat.title;
    NEW.factor = cat.factor;
    NEW.registration = (SELECT v.registration FROM vehicles v WHERE v.id = NEW.vehicle_id);

RETURN NEW;
END;
$$;

CREATE FUNCTION public.before_insert_or_update_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    cat RECORD;
BEGIN
    IF NEW.category_id IS NOT NULL THEN
        SELECT title, factor INTO cat FROM categories WHERE id = NEW.category_id;
        NEW.category = cat.title;

-- Validate factor matches: deny if category has a factor that differs from entry's factor
        IF cat.factor IS NOT NULL AND cat.factor <> NEW.factor THEN
            RAISE EXCEPTION 'Entry factor ''%'' does not match category factor ''%''', NEW.factor, cat.factor;
        END IF;
    ELSE
        NEW.category = NULL;
    END IF;

RETURN NEW;
END;
$$;

CREATE FUNCTION public.before_insert_or_update_user() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.role_id IS NOT NULL THEN
        NEW.permissions = COALESCE((SELECT array_agg(p.title)
                           FROM permissions p
                           JOIN roles r ON p.id = ANY(r.permissions)
                           WHERE r.id = NEW.role_id), '{}');
    END IF;
    NEW.role = (SELECT r.title FROM roles r WHERE r.id = NEW.role_id);
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.insert_or_update_entry() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE entry RECORD;
BEGIN
    SELECT * INTO entry FROM entries WHERE id = NEW.entry_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Entry not found';
    END IF;
    IF entry.factor = 'plus' THEN
        NEW.plus = NEW.amount;
    ELSE
        NEW.minus = abs(NEW.amount);
        NEW.amount = -NEW.minus;
        NEW.registration = (SELECT registration FROM vehicles WHERE id = NEW.vehicle_id);
    END IF;
    NEW.week = NEW.date + (6 - extract(dow from NEW.date)) * interval '1 day';
    NEW.name = entry.title;
    NEW.position = entry.position;
    NEW.category_id = entry.category_id;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.insert_or_update_petty_cash() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE entry entries%ROWTYPE; vehicle vehicles%ROWTYPE;
BEGIN
    IF NEW.credit_note IS TRUE THEN
        -- Credit notes carry only `minus` (cash out) plus a description.
        IF NEW.minus IS NULL OR NEW.plus IS NOT NULL OR NEW.unit_price IS NOT NULL OR NEW.quantity IS NOT NULL THEN
            RAISE EXCEPTION 'Credit notes require minus only (no plus/unit_price/quantity)';
        END IF;
    ELSIF (NEW.plus IS NULL AND NEW.unit_price IS NULL AND NEW.quantity IS NULL) OR (NEW.plus IS NOT NULL AND NEW.unit_price IS NOT NULL AND NEW.quantity IS NOT NULL) THEN
        RAISE EXCEPTION 'Either cash or unit price and quantity must be provided';
    END IF;
    IF NEW.entry_id IS NOT NULL THEN
        SELECT  title, factor, category_id, category INTO entry.title, entry.factor, entry.category_id, entry.category FROM entries WHERE id = NEW.entry_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Entry not found';
        END IF;
        IF entry.factor != 'minus' THEN
            RAISE EXCEPTION 'Entry factor must be minus';
        END IF;
        NEW.name = entry.title;
        NEW.category_id = entry.category_id;
        NEW.category = entry.category;
        NEW.minus = NEW.quantity * NEW.unit_price;
    END IF;
    IF NEW.vehicle_id IS NOT NULL THEN
        SELECT registration into vehicle.registration FROM vehicles WHERE id = NEW.vehicle_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Vehicle not found';
        END IF;
        NEW.registration = vehicle.registration;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.set_vehicle_provision_cf() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_balance DOUBLE PRECISION;
BEGIN
    -- Get current provision balance with row lock
    SELECT provision_cf INTO v_balance
    FROM vehicles WHERE id = NEW.vehicle_id
    FOR UPDATE;

IF v_balance IS NULL THEN
        RAISE EXCEPTION 'Vehicle % not found', NEW.vehicle_id;
    END IF;

-- Calculate balance after this entry
    IF NEW.entry_type = 'DEPOSIT' THEN
        NEW.balance_after := v_balance + NEW.amount;
    ELSIF NEW.entry_type = 'WITHDRAWAL' THEN
        IF v_balance < NEW.amount THEN
            RAISE EXCEPTION 'Insufficient provision balance: available=%, requested=%', v_balance, NEW.amount;
        END IF;
        NEW.balance_after := v_balance - NEW.amount;
    ELSE
        RAISE EXCEPTION 'Invalid entry_type: %', NEW.entry_type;
    END IF;

RETURN NEW;
END;
$$;

CREATE FUNCTION public.update_vehicle_provision_cf() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.entry_type = 'DEPOSIT' THEN
        UPDATE vehicles
        SET provision_cf = provision_cf + NEW.amount,
            updated_at = NOW()
        WHERE id = NEW.vehicle_id;
    ELSIF NEW.entry_type = 'WITHDRAWAL' THEN
        UPDATE vehicles
        SET provision_cf = provision_cf - NEW.amount,
            updated_at = NOW()
        WHERE id = NEW.vehicle_id;
    END IF;

RETURN NEW;
END;
$$;

SET default_tablespace = '';

SET default_table_access_method = heap;

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);

CREATE TABLE public.budgets (
    category_id uuid NOT NULL,
    category character varying(50) NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL,
    budget double precision DEFAULT '0'::double precision NOT NULL,
    actual double precision DEFAULT '0'::double precision NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    vehicle_id uuid NOT NULL,
    registration character varying(20) NOT NULL,
    factor public.factor_enum
);

CREATE TABLE public.categories (
    title character varying(50) NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    factor public.factor_enum
);

CREATE TABLE public.entries (
    title character varying(50) NOT NULL,
    "position" integer,
    factor public.factor_enum NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    "primary" boolean DEFAULT false NOT NULL,
    category_id uuid,
    category character varying(50)
);

CREATE TABLE public.password_reset_codes (
    user_id uuid NOT NULL,
    phone_number character varying(20) NOT NULL,
    reset_code character varying(6) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    is_used boolean NOT NULL,
    attempts integer NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone
);

CREATE TABLE public.permissions (
    title character varying(50) NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone
);

CREATE TABLE public.petty_cash (
    entry_id uuid,
    vehicle_id uuid,
    registration character varying(20),
    name character varying(50) NOT NULL,
    unit_price double precision,
    quantity double precision,
    plus double precision,
    minus double precision,
    date date NOT NULL,
    committed boolean DEFAULT false NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    category_id uuid,
    category character varying(50),
    source character varying(100),
    manager_id uuid,
    credit_note boolean DEFAULT false NOT NULL,
    description character varying(500)
);

CREATE TABLE public.petty_cash_daily_balances (
    date date NOT NULL,
    opening_balance double precision DEFAULT '0'::double precision NOT NULL,
    closing_balance double precision DEFAULT '0'::double precision NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone
);

CREATE TABLE public.provisions (
    vehicle_id uuid NOT NULL,
    registration character varying(50),
    amount double precision NOT NULL,
    entry_type character varying(20) NOT NULL,
    date date NOT NULL,
    description character varying(200),
    balance_after double precision NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone
);

CREATE TABLE public.records (
    entry_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    name character varying(50) NOT NULL,
    plus double precision,
    minus double precision,
    amount double precision NOT NULL,
    date date NOT NULL,
    week date NOT NULL,
    "position" integer,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    locked boolean DEFAULT false NOT NULL,
    quantity double precision DEFAULT '1'::double precision NOT NULL,
    registration character varying(20),
    category_id uuid,
    petty_cash_id uuid
);

CREATE TABLE public.roles (
    title character varying(50) NOT NULL,
    permissions uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    is_system_role boolean DEFAULT false NOT NULL
);

CREATE TABLE public.users (
    name character varying(191) NOT NULL,
    email character varying(191) NOT NULL,
    password character varying(191) NOT NULL,
    phone character varying(191),
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    role_id uuid,
    permissions character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    role character varying(50),
    petty_cash_backdate_days integer DEFAULT 7 NOT NULL,
    is_default_petty_cash_manager boolean DEFAULT false NOT NULL
);

CREATE TABLE public.vehicles (
    registration character varying(50) NOT NULL,
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at timestamp with time zone,
    sacco character varying(50),
    provision_bf double precision DEFAULT '0'::double precision NOT NULL,
    provision_cf double precision DEFAULT '0'::double precision NOT NULL
);

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

ALTER TABLE ONLY public.budgets
    ADD CONSTRAINT budgets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_title_key UNIQUE (title);

ALTER TABLE ONLY public.entries
    ADD CONSTRAINT entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.password_reset_codes
    ADD CONSTRAINT password_reset_codes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.petty_cash_daily_balances
    ADD CONSTRAINT petty_cash_daily_balances_date_key UNIQUE (date);

ALTER TABLE ONLY public.petty_cash_daily_balances
    ADD CONSTRAINT petty_cash_daily_balances_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.petty_cash
    ADD CONSTRAINT petty_cash_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.provisions
    ADD CONSTRAINT provisions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_petty_cash_id_key UNIQUE (petty_cash_id);

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.budgets
    ADD CONSTRAINT unique_budget_per_category_per_month UNIQUE (vehicle_id, category_id, year, month);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_pkey PRIMARY KEY (id);

CREATE INDEX ix_provisions_vehicle_id ON public.provisions USING btree (vehicle_id);

CREATE TRIGGER after_insert_or_update_record AFTER INSERT OR UPDATE ON public.records FOR EACH ROW EXECUTE FUNCTION public.after_insert_or_update_record();

CREATE TRIGGER after_insert_update_petty_cash AFTER INSERT OR DELETE OR UPDATE ON public.petty_cash FOR EACH ROW EXECUTE FUNCTION public.after_insert_update_petty_cash();

CREATE TRIGGER after_update_category AFTER UPDATE ON public.categories FOR EACH ROW EXECUTE FUNCTION public.after_update_category();

CREATE TRIGGER after_update_entry AFTER UPDATE ON public.entries FOR EACH ROW EXECUTE FUNCTION public.after_update_entry();

CREATE TRIGGER after_update_role_trigger AFTER UPDATE ON public.roles FOR EACH ROW EXECUTE FUNCTION public.after_update_role_trigger_function();

CREATE TRIGGER after_update_vehicle AFTER UPDATE ON public.vehicles FOR EACH ROW EXECUTE FUNCTION public.after_update_vehicle();

CREATE TRIGGER before_delete_record BEFORE DELETE ON public.records FOR EACH ROW EXECUTE FUNCTION public.before_delete_record();

CREATE TRIGGER before_insert_or_update_budget BEFORE INSERT OR UPDATE ON public.budgets FOR EACH ROW EXECUTE FUNCTION public.before_insert_or_update_budget();

CREATE TRIGGER before_insert_or_update_entry BEFORE INSERT OR UPDATE ON public.entries FOR EACH ROW EXECUTE FUNCTION public.before_insert_or_update_entry();

CREATE TRIGGER before_insert_or_update_user BEFORE INSERT OR UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.before_insert_or_update_user();

CREATE TRIGGER insert_or_update_petty_cash BEFORE INSERT OR UPDATE ON public.petty_cash FOR EACH ROW EXECUTE FUNCTION public.insert_or_update_petty_cash();

CREATE TRIGGER insert_or_update_record BEFORE INSERT OR UPDATE ON public.records FOR EACH ROW EXECUTE FUNCTION public.insert_or_update_entry();

CREATE TRIGGER provision_after_insert AFTER INSERT ON public.provisions FOR EACH ROW EXECUTE FUNCTION public.update_vehicle_provision_cf();

CREATE TRIGGER provision_before_insert BEFORE INSERT ON public.provisions FOR EACH ROW EXECUTE FUNCTION public.set_vehicle_provision_cf();

ALTER TABLE ONLY public.budgets
    ADD CONSTRAINT budgets_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.budgets
    ADD CONSTRAINT budgets_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.entries
    ADD CONSTRAINT entries_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.petty_cash
    ADD CONSTRAINT fk_petty_cash_manager_id_users FOREIGN KEY (manager_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.password_reset_codes
    ADD CONSTRAINT password_reset_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.petty_cash
    ADD CONSTRAINT petty_cash_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.petty_cash
    ADD CONSTRAINT petty_cash_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.entries(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.petty_cash
    ADD CONSTRAINT petty_cash_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.provisions
    ADD CONSTRAINT provisions_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.entries(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_petty_cash_id_fkey FOREIGN KEY (petty_cash_id) REFERENCES public.petty_cash(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;
