CREATE TABLE "job_manager"."addresses" (
    "id" integer DEFAULT nextval('job_manager.addresses_id_seq'::regclass) NOT NULL,
    "address_line" character varying(255) NOT NULL,
    "city" character varying(100) NOT NULL,
    "state" character varying(100) NOT NULL,
    "zip_code" character varying(20) NOT NULL
);

ALTER TABLE "job_manager"."addresses" ADD CONSTRAINT "addresses_pkey" PRIMARY KEY (id);

CREATE UNIQUE INDEX addresses_pkey ON job_manager.addresses USING btree (id);
