BEGIN;

CREATE SCHEMA IF NOT EXISTS "job_manager";

DROP TABLE IF EXISTS "job_manager"."user_roles" CASCADE;

CREATE TABLE "job_manager"."user_roles" (
    "id" integer DEFAULT nextval('job_manager.user_roles_id_seq'::regclass) NOT NULL,
    "user_id" integer NOT NULL,
    "role_id" integer NOT NULL
);

ALTER TABLE "job_manager"."user_roles" ADD CONSTRAINT "user_roles_pkey" PRIMARY KEY (id);
ALTER TABLE "job_manager"."user_roles" ADD CONSTRAINT "user_roles_role_id_fkey" FOREIGN KEY (role_id) REFERENCES "job_manager"."roles" (id) ON UPDATE NO ACTION ON DELETE CASCADE;
ALTER TABLE "job_manager"."user_roles" ADD CONSTRAINT "user_roles_user_id_fkey" FOREIGN KEY (user_id) REFERENCES "job_manager"."users" (id) ON UPDATE NO ACTION ON DELETE CASCADE;

CREATE UNIQUE INDEX user_roles_pkey ON job_manager.user_roles USING btree (id);
CREATE INDEX userrole_role_id ON job_manager.user_roles USING btree (role_id);
CREATE INDEX userrole_user_id ON job_manager.user_roles USING btree (user_id);
CREATE UNIQUE INDEX userrole_user_id_role_id ON job_manager.user_roles USING btree (user_id, role_id);

INSERT INTO "job_manager"."user_roles" ("id", "user_id", "role_id") VALUES (1, 1, 1);

COMMIT;
