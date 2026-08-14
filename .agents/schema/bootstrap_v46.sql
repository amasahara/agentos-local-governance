-- AgentOS schema bootstrap baseline v46
-- Generated deterministically from the v0.24.3 migration chain.
-- schema_migrations is created/seeded by runtime code.

-- table: async_jobs
CREATE TABLE async_jobs(
        job_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, session_id TEXT NOT NULL,
        spec_json TEXT NOT NULL, spec_hash TEXT NOT NULL, state TEXT NOT NULL,
        pid INTEGER, exit_code INTEGER, timeout_seconds INTEGER NOT NULL,
        stdout_path TEXT NOT NULL, stderr_path TEXT NOT NULL, cancel_reason TEXT,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT, finished_at TEXT, FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: audit_events
CREATE TABLE audit_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        task_id TEXT,
        session_id TEXT,
        payload_json TEXT NOT NULL,
        previous_hash TEXT,
        event_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

-- table: audit_key_rotations
CREATE TABLE audit_key_rotations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        old_key_id TEXT NOT NULL,
        new_key_id TEXT NOT NULL,
        identity TEXT NOT NULL,
        reason TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        rotated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

-- table: audit_segments
CREATE TABLE audit_segments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, first_event_id INTEGER NOT NULL, last_event_id INTEGER NOT NULL,
        event_count INTEGER NOT NULL, first_event_hash TEXT, last_event_hash TEXT, segment_hash TEXT NOT NULL,
        archive_path TEXT NOT NULL, signature TEXT, status TEXT NOT NULL DEFAULT 'verified',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: authenticated_requests
CREATE TABLE authenticated_requests(
        request_id TEXT PRIMARY KEY, token_id TEXT NOT NULL, task_id TEXT NOT NULL,
        session_id TEXT NOT NULL, sequence INTEGER NOT NULL, body_hash TEXT NOT NULL,
        decision TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: backup_manifests
CREATE TABLE backup_manifests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, backup_path TEXT NOT NULL, manifest_hash TEXT NOT NULL,
        authoritative_json TEXT NOT NULL, rebuildable_json TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: canonical_entities
CREATE TABLE canonical_entities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            exact_key_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL, key_id TEXT, privacy_status TEXT NOT NULL DEFAULT 'active', tombstoned_at TEXT, erasure_request_hash TEXT,
            UNIQUE(consolidation_id,target_schema,target_table,exact_key_fingerprint)
        );

-- table: claim_evidence
CREATE TABLE claim_evidence(
        claim_id INTEGER NOT NULL,
        tool_call_id INTEGER NOT NULL,
        evidence_role TEXT NOT NULL DEFAULT 'supports',
        FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE CASCADE,
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id),
        PRIMARY KEY(claim_id, tool_call_id, evidence_role)
    );

-- table: claims
CREATE TABLE claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        claim_text TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        risk TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: context_budget_decisions
CREATE TABLE context_budget_decisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_revision INTEGER NOT NULL,
            model_profile TEXT NOT NULL,
            model_profile_hash TEXT NOT NULL,
            budget_mode TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            control_tokens INTEGER NOT NULL,
            reserved_output INTEGER NOT NULL,
            system_tool_overhead INTEGER NOT NULL,
            safety_margin INTEGER NOT NULL,
            calibration_headroom INTEGER NOT NULL,
            input_budget INTEGER NOT NULL,
            evidence_budget INTEGER NOT NULL,
            evidence_floor INTEGER NOT NULL,
            evidence_floor_satisfied INTEGER NOT NULL,
            pressure_score REAL NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id,transport_revision)
        );

-- table: context_compression_comparisons
CREATE TABLE context_compression_comparisons(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            baseline_pack_id INTEGER NOT NULL,
            candidate_pack_id INTEGER NOT NULL,
            comparison_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            regression_flags_json TEXT NOT NULL,
            comparison_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(baseline_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(candidate_pack_id) REFERENCES context_transport_packs(id)
        );

-- table: context_compression_evaluation_runs
CREATE TABLE context_compression_evaluation_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            transport_hash TEXT NOT NULL,
            evaluation_version INTEGER NOT NULL,
            evaluation_hash TEXT NOT NULL,
            gate_status TEXT NOT NULL,
            hard_failures_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            canonical_candidate_count INTEGER NOT NULL,
            included_candidate_count INTEGER NOT NULL,
            expandable_candidate_count INTEGER NOT NULL,
            accounted_candidate_count INTEGER NOT NULL,
            unaccounted_candidate_count INTEGER NOT NULL,
            handle_integrity_rate REAL NOT NULL,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            requirement_preservation_rate REAL NOT NULL,
            context_miss_count INTEGER NOT NULL,
            expansion_request_count INTEGER NOT NULL,
            expansion_success_count INTEGER NOT NULL,
            expansion_failure_count INTEGER NOT NULL,
            budget_utilization REAL NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(transport_pack_id,evaluation_hash)
        );

-- table: context_expansion_events
CREATE TABLE context_expansion_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            handle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            source_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, session_id INTEGER, request_hash TEXT, line_start INTEGER, line_end INTEGER, returned_tokens INTEGER, reason_code TEXT, requirement_ids_json TEXT, transport_hash TEXT,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

-- table: context_expansion_sessions
CREATE TABLE context_expansion_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            transport_hash TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            requirement_ids_json TEXT NOT NULL,
            requested_handle_count INTEGER NOT NULL,
            expanded_handle_count INTEGER NOT NULL,
            failed_handle_count INTEGER NOT NULL,
            returned_tokens INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

-- table: context_knowledge_events
CREATE TABLE context_knowledge_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, context_revision INTEGER,
        candidate_count INTEGER NOT NULL, included_count INTEGER NOT NULL, omitted_count INTEGER NOT NULL,
        fallback_used INTEGER NOT NULL DEFAULT 0, manifest_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: context_model_profile_snapshots
CREATE TABLE context_model_profile_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_version INTEGER NOT NULL,
            context_capacity INTEGER NOT NULL,
            tokenizer_policy TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_name,profile_hash)
        );

-- table: context_packs
CREATE TABLE context_packs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
        manifest_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id), UNIQUE(task_id,revision));

-- table: context_requirement_ledger
CREATE TABLE context_requirement_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            requirement_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            source_kind TEXT NOT NULL,
            exact_text TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            span_start INTEGER,
            span_end INTEGER,
            protected INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id, context_revision, requirement_id)
        );

-- table: context_token_observations
CREATE TABLE context_token_observations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            transport_pack_id INTEGER,
            model_profile TEXT NOT NULL,
            model_profile_hash TEXT NOT NULL,
            tokenizer_id TEXT NOT NULL,
            predicted_input_tokens INTEGER NOT NULL,
            observed_input_tokens INTEGER NOT NULL,
            predicted_output_reserve INTEGER NOT NULL,
            observed_output_tokens INTEGER,
            underestimation_tokens INTEGER NOT NULL,
            underestimation_ratio REAL NOT NULL,
            source TEXT NOT NULL,
            observation_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            UNIQUE(transport_pack_id,source)
        );

-- table: context_transport_evaluations
CREATE TABLE context_transport_evaluations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            protected_requirement_count INTEGER NOT NULL,
            preserved_requirement_count INTEGER NOT NULL,
            requirement_preservation_rate REAL NOT NULL,
            context_miss_count INTEGER NOT NULL,
            expansion_request_count INTEGER NOT NULL,
            task_success_rate REAL,
            test_pass_rate REAL,
            rework_count INTEGER,
            tool_call_count INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

-- table: context_transport_packs
CREATE TABLE context_transport_packs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_revision INTEGER NOT NULL,
            transport_version INTEGER NOT NULL,
            status TEXT NOT NULL,
            model_profile TEXT NOT NULL,
            tokenizer_id TEXT NOT NULL,
            original_request_hash TEXT NOT NULL,
            authority_hash TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            plan_hash TEXT,
            source_freshness_hash TEXT NOT NULL,
            transport_hash TEXT,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            control_tokens INTEGER NOT NULL,
            evidence_tokens INTEGER NOT NULL,
            token_budget INTEGER NOT NULL,
            saved_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            preservation_rate REAL NOT NULL,
            manifest_json TEXT NOT NULL,
            failure_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, model_profile_hash TEXT, budget_mode TEXT NOT NULL DEFAULT 'fixed', budget_decision_id INTEGER,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id, transport_revision)
        );

-- table: coordination_events
CREATE TABLE coordination_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, session_id TEXT NOT NULL,
        event_type TEXT NOT NULL, resource_type TEXT, resource_key TEXT, lease_id INTEGER,
        decision TEXT NOT NULL, reason TEXT, payload_hash TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id), FOREIGN KEY(lease_id) REFERENCES resource_leases(id));

-- table: data_subject_erasure_approvals
CREATE TABLE data_subject_erasure_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            approval_hash TEXT NOT NULL UNIQUE,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );

-- table: data_subject_erasure_events
CREATE TABLE data_subject_erasure_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            plan_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            governed_operation_id TEXT,
            external_event_hash TEXT
        );

-- table: data_subject_erasure_executions
CREATE TABLE data_subject_erasure_executions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            execution_uuid TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('completed','failed')),
            local_erasure_completed INTEGER NOT NULL CHECK(local_erasure_completed IN (0,1)),
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            deleted_counts_json TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            executed_by TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            failure_code TEXT,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );

-- table: data_subject_erasure_plans
CREATE TABLE data_subject_erasure_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            request_id INTEGER NOT NULL UNIQUE,
            policy_version INTEGER NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            affected_counts_json TEXT NOT NULL,
            affected_artifact_hashes_json TEXT NOT NULL,
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(request_id) REFERENCES data_subject_erasure_requests(id)
        );

-- table: data_subject_erasure_requests
CREATE TABLE data_subject_erasure_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_uuid TEXT NOT NULL UNIQUE,
            canonical_entity_id INTEGER NOT NULL,
            entity_uuid TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            request_hash TEXT NOT NULL UNIQUE,
            requested_by TEXT NOT NULL,
            created_at TEXT NOT NULL, entity_locator_hash TEXT,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id)
        );

-- table: data_subject_erasure_reviews
CREATE TABLE data_subject_erasure_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            decision TEXT NOT NULL CHECK(decision IN ('reviewed','rejected')),
            reviewed_by TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );

-- table: db_boundary_events
CREATE TABLE db_boundary_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        , governed_operation_id TEXT, external_event_hash TEXT);

-- table: db_connections
CREATE TABLE db_connections(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_uuid TEXT NOT NULL UNIQUE,
            connection_alias TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            engine TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            database_name TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            credential_ref TEXT NOT NULL,
            tls_required INTEGER NOT NULL DEFAULT 1,
            readonly_verified INTEGER NOT NULL DEFAULT 0,
            readonly_verification_method TEXT,
            readonly_verified_by TEXT,
            readonly_verified_at TEXT,
            data_write_enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

-- table: db_consolidation_sources
CREATE TABLE db_consolidation_sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            readonly_verified_at_registration INTEGER NOT NULL,
            registered_by TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            UNIQUE(consolidation_id, source_connection_id)
        );

-- table: db_consolidations
CREATE TABLE db_consolidations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_connection_id INTEGER NOT NULL,
            domain_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id)
        );

-- table: db_extraction_batch_mappings
CREATE TABLE db_extraction_batch_mappings(
            batch_id INTEGER NOT NULL,
            mapping_id INTEGER NOT NULL,
            mapping_hash TEXT NOT NULL,
            PRIMARY KEY(batch_id, mapping_id),
            FOREIGN KEY(batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(mapping_id) REFERENCES db_field_mappings(id)
        );

-- table: db_extraction_batches
CREATE TABLE db_extraction_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            extraction_plan_version INTEGER NOT NULL,
            extraction_plan_json TEXT NOT NULL,
            extraction_plan_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            max_rows INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            selected_rows INTEGER NOT NULL DEFAULT 0,
            valid_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            staging_path TEXT,
            staging_hash TEXT,
            quarantine_path TEXT,
            quarantine_hash TEXT,
            manifest_path TEXT,
            manifest_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            failure_reason TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(source_snapshot_id) REFERENCES db_schema_snapshots(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );

-- table: db_extraction_events
CREATE TABLE db_extraction_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            consolidation_id INTEGER,
            source_connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        , governed_operation_id TEXT, external_event_hash TEXT);

-- table: db_field_mappings
CREATE TABLE db_field_mappings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_column TEXT NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_column TEXT NOT NULL,
            source_canonical_type TEXT NOT NULL,
            target_canonical_type TEXT NOT NULL,
            type_compatibility TEXT NOT NULL,
            transform_rule TEXT,
            transform_output_type TEXT,
            validation_rule_json TEXT,
            confidence REAL NOT NULL,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            mapping_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confirmed_by TEXT,
            confirmed_at TEXT,
            rejected_by TEXT,
            rejected_at TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(source_snapshot_id) REFERENCES db_schema_snapshots(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id),
            UNIQUE(consolidation_id, source_snapshot_id, target_contract_id, source_schema, source_table, source_column, target_schema, target_table, target_column)
        );

-- table: db_reconciliation_findings
CREATE TABLE db_reconciliation_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_run_id INTEGER NOT NULL,
            finding_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            count_value INTEGER NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );

-- table: db_reconciliation_runs
CREATE TABLE db_reconciliation_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_uuid TEXT NOT NULL UNIQUE,
            insert_run_id INTEGER NOT NULL,
            reconciliation_version INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            plan_hash TEXT NOT NULL,
            expected_row_count INTEGER NOT NULL,
            expected_row_set_hash TEXT NOT NULL,
            observed_row_count INTEGER NOT NULL DEFAULT 0,
            observed_row_set_hash TEXT,
            matching_rows INTEGER NOT NULL DEFAULT 0,
            missing_rows INTEGER NOT NULL DEFAULT 0,
            unexpected_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            outcome TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            evidence_hash TEXT,
            started_at TEXT,
            completed_at TEXT,
            failure_reason TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );

-- table: db_recovery_cases
CREATE TABLE db_recovery_cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_uuid TEXT NOT NULL UNIQUE,
            insert_run_id INTEGER NOT NULL,
            reconciliation_run_id INTEGER,
            case_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            evidence_hash TEXT,
            decision TEXT,
            decided_by TEXT,
            decided_at TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id),
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );

-- table: db_recovery_checkpoints
CREATE TABLE db_recovery_checkpoints(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER NOT NULL,
            reconciliation_run_id INTEGER,
            checkpoint_type TEXT NOT NULL,
            checkpoint_hash TEXT NOT NULL,
            checkpoint_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id),
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );

-- table: db_recovery_events
CREATE TABLE db_recovery_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER,
            reconciliation_run_id INTEGER,
            recovery_case_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        , governed_operation_id TEXT, external_event_hash TEXT);

-- table: db_schema_mapping_events
CREATE TABLE db_schema_mapping_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            snapshot_id INTEGER,
            contract_id INTEGER,
            mapping_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        , governed_operation_id TEXT, external_event_hash TEXT);

-- table: db_schema_snapshots
CREATE TABLE db_schema_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_uuid TEXT NOT NULL UNIQUE,
            connection_id INTEGER NOT NULL,
            connection_role TEXT NOT NULL,
            engine TEXT NOT NULL,
            manifest_version INTEGER NOT NULL,
            manifest_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            table_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            captured_by TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            FOREIGN KEY(connection_id) REFERENCES db_connections(id)
        );

-- table: db_target_insert_events
CREATE TABLE db_target_insert_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER,
            extraction_batch_id INTEGER,
            consolidation_id INTEGER,
            target_connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL, governed_operation_id TEXT, external_event_hash TEXT,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );

-- table: db_target_insert_runs
CREATE TABLE db_target_insert_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_uuid TEXT NOT NULL UNIQUE,
            extraction_batch_id INTEGER NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            insert_plan_version INTEGER NOT NULL,
            insert_plan_json TEXT NOT NULL,
            insert_plan_hash TEXT NOT NULL,
            staging_path TEXT NOT NULL,
            staging_hash TEXT NOT NULL,
            staging_manifest_hash TEXT NOT NULL,
            extraction_plan_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            target_snapshot_hash TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_order_json TEXT NOT NULL,
            chunk_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            started_at TEXT,
            committing_at TEXT,
            committed_at TEXT,
            failed_at TEXT,
            failure_stage TEXT,
            failure_reason TEXT,
            attempted_rows INTEGER NOT NULL DEFAULT 0,
            committed_rows INTEGER NOT NULL DEFAULT 0,
            commit_receipt_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL, lineage_status TEXT NOT NULL DEFAULT 'not_required_v0220', lineage_finalized_at TEXT,
            FOREIGN KEY(extraction_batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );

-- table: db_validation_findings
CREATE TABLE db_validation_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            row_ordinal INTEGER NOT NULL,
            source_locator_hash TEXT NOT NULL,
            target_field TEXT,
            rule_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value_hash TEXT,
            raw_value_stored INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES db_extraction_batches(id)
        );

-- table: egress_events
CREATE TABLE egress_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        target TEXT,
        reason_code TEXT,
        justification TEXT,
        decision TEXT NOT NULL,
        success INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: evaluation_runs
CREATE TABLE evaluation_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, metrics_schema_version INTEGER NOT NULL,
        agent_name TEXT, model_name TEXT, policy_version TEXT NOT NULL,
        repository_version TEXT NOT NULL, filters_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: evolution_proposals
CREATE TABLE evolution_proposals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, status TEXT NOT NULL,
        trigger_findings_json TEXT NOT NULL, policy_patch_json TEXT NOT NULL,
        expected_benefit TEXT NOT NULL, risks_json TEXT NOT NULL, rollback_plan_json TEXT NOT NULL,
        baseline_evaluation_run_id INTEGER NOT NULL, simulation_json TEXT, proposal_hash TEXT NOT NULL UNIQUE,
        created_by TEXT NOT NULL, reviewed_by TEXT, review_note TEXT, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(baseline_evaluation_run_id) REFERENCES evaluation_runs(id));

-- table: evolution_stage_events
CREATE TABLE evolution_stage_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER NOT NULL, from_status TEXT NOT NULL,
        to_status TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(proposal_id) REFERENCES evolution_proposals(id));

-- table: execution_manifests
CREATE TABLE execution_manifests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        session_id TEXT NOT NULL, command_hash TEXT NOT NULL, cwd TEXT NOT NULL,
        sandbox_profile TEXT NOT NULL, workspace_path TEXT,
        environment_hash TEXT NOT NULL, network_allowed INTEGER NOT NULL DEFAULT 0,
        decision TEXT NOT NULL, reason TEXT, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: external_audit_checkpoints
CREATE TABLE external_audit_checkpoints(
        project_id TEXT PRIMARY KEY,
        last_sequence INTEGER NOT NULL,
        last_event_hash TEXT NOT NULL,
        key_id TEXT NOT NULL,
        verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

-- table: file_read_cache
CREATE TABLE file_read_cache(
        task_id TEXT NOT NULL,
        path TEXT NOT NULL,
        range_key TEXT NOT NULL,
        mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        summary TEXT NOT NULL,
        accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(task_id, path, range_key),
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: file_versions
CREATE TABLE file_versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        version INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        previous_hash TEXT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        lease_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(lease_id) REFERENCES resource_leases(id),
        UNIQUE(path,version)
    );

-- table: gateway_state
CREATE TABLE gateway_state(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), instance_id TEXT NOT NULL,
        security_profile TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: governance_baseline
CREATE TABLE governance_baseline(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        acknowledged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        acknowledged_by TEXT NOT NULL DEFAULT 'human',
        git_commit TEXT
    , acknowledgement_method TEXT NOT NULL DEFAULT 'legacy', session_id TEXT);

-- table: governance_change_log
CREATE TABLE governance_change_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        old_hash TEXT,
        new_hash TEXT NOT NULL,
        detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        detected_by TEXT NOT NULL,
        task_id TEXT,
        acknowledged INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: governed_operations
CREATE TABLE governed_operations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        intent_hash TEXT NOT NULL,
        execution_token_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        denial_reason TEXT,
        external_request_hash TEXT,
        external_completion_hash TEXT,
        success INTEGER,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: guarded_executions
CREATE TABLE guarded_executions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        execution_token TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        classification TEXT NOT NULL,
        args_hash TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        target TEXT,
        reason_code TEXT,
        justification TEXT,
        issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        completed_at TEXT,
        success INTEGER,
        tool_call_id INTEGER,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id)
    );

-- table: identity_bindings
CREATE TABLE identity_bindings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL,
            resolution_run_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_locator_hash TEXT NOT NULL,
            source_record_token TEXT NOT NULL UNIQUE,
            exact_key_fingerprint TEXT NOT NULL,
            strong_fingerprint TEXT,
            decision_type TEXT NOT NULL,
            decision_id INTEGER,
            created_at TEXT NOT NULL, key_id TEXT,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id),
            FOREIGN KEY(resolution_run_id) REFERENCES identity_resolution_runs(id)
        );

-- table: identity_candidates
CREATE TABLE identity_candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolution_run_id INTEGER NOT NULL,
            source_record_token TEXT NOT NULL,
            matched_entity_uuid TEXT NOT NULL,
            candidate_hash TEXT NOT NULL UNIQUE,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_by TEXT,
            decided_at TEXT,
            created_at TEXT NOT NULL, key_id TEXT,
            FOREIGN KEY(resolution_run_id) REFERENCES identity_resolution_runs(id)
        );

-- table: identity_resolution_events
CREATE TABLE identity_resolution_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id INTEGER,
            resolution_run_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        , governed_operation_id TEXT, external_event_hash TEXT);

-- table: identity_resolution_policies
CREATE TABLE identity_resolution_policies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            policy_json TEXT NOT NULL,
            policy_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );

-- table: identity_resolution_runs
CREATE TABLE identity_resolution_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolution_uuid TEXT NOT NULL UNIQUE,
            extraction_batch_id INTEGER NOT NULL UNIQUE,
            policy_id INTEGER NOT NULL,
            input_staging_path TEXT NOT NULL,
            input_staging_hash TEXT NOT NULL,
            output_staging_path TEXT,
            output_staging_hash TEXT,
            manifest_path TEXT,
            manifest_hash TEXT,
            input_rows INTEGER NOT NULL DEFAULT 0,
            output_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            failure_reason TEXT, key_id TEXT,
            FOREIGN KEY(extraction_batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(policy_id) REFERENCES identity_resolution_policies(id)
        );

-- table: job_events
CREATE TABLE job_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
        event_type TEXT NOT NULL, details_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES async_jobs(job_id));

-- table: knowledge_edges
CREATE TABLE knowledge_edges(
        edge_id TEXT PRIMARY KEY, from_node_id TEXT NOT NULL, to_node_id TEXT NOT NULL,
        relation TEXT NOT NULL, evidence_json TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'active', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(from_node_id) REFERENCES knowledge_nodes(node_id),
        FOREIGN KEY(to_node_id) REFERENCES knowledge_nodes(node_id));

-- table: knowledge_embeddings
CREATE TABLE knowledge_embeddings(
        source_kind TEXT NOT NULL, source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
        backend TEXT NOT NULL, dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL,
        text_snapshot TEXT NOT NULL, metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, vector_blob BLOB, vector_dtype TEXT NOT NULL DEFAULT 'float32', vector_version INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(source_kind,source_id,backend));

-- table: knowledge_nodes
CREATE TABLE knowledge_nodes(
        node_id TEXT PRIMARY KEY, node_type TEXT NOT NULL, label TEXT NOT NULL,
        properties_json TEXT NOT NULL, content_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: knowledge_retrieval_events
CREATE TABLE knowledge_retrieval_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, query_hash TEXT NOT NULL,
        backend TEXT NOT NULL, kinds_json TEXT NOT NULL, limit_value INTEGER NOT NULL,
        result_count INTEGER NOT NULL, result_ids_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: lineage_key_rotation_plans
CREATE TABLE lineage_key_rotation_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            predecessor_key_id TEXT NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('planned','reviewed','approved','executed','cancelled')),
            reason_hash TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            executed_by TEXT,
            executed_at TEXT,
            new_key_id TEXT
        );

-- table: lineage_keys
CREATE TABLE lineage_keys(
            key_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK(status IN ('active','retired','revoked')),
            material_path TEXT NOT NULL,
            material_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            activated_at TEXT,
            retired_at TEXT,
            revoked_at TEXT,
            predecessor_key_id TEXT,
            rotation_plan_id INTEGER,
            provenance TEXT NOT NULL
        );

-- table: lineage_rekey_plans
CREATE TABLE lineage_rekey_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            source_connection_id INTEGER NOT NULL,
            from_key_id TEXT NOT NULL,
            to_key_id TEXT NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('planned','reviewed','approved','ready_for_source_reread','completed','cancelled')),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            completed_at TEXT
        );

-- table: policy_override_approvals
CREATE TABLE policy_override_approvals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reviewed_by TEXT,
        review_method TEXT,
        reviewed_at TEXT,
        note TEXT,
        UNIQUE(content_hash)
    );

-- table: precommit_checks
CREATE TABLE precommit_checks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ok INTEGER NOT NULL,
        changed_files_json TEXT NOT NULL, blockers_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: primary_project_selections
CREATE TABLE primary_project_selections(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL UNIQUE,
            primary_project_uuid TEXT NOT NULL,
            selected_by TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            selection_reason TEXT NOT NULL,
            recommendation_json TEXT NOT NULL,
            selection_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'selected',
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id)
        );

-- table: privacy_tombstones
CREATE TABLE privacy_tombstones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL UNIQUE,
            tombstone_uuid TEXT NOT NULL UNIQUE,
            request_hash TEXT NOT NULL,
            plan_hash TEXT NOT NULL,
            tombstone_marker_hash TEXT NOT NULL UNIQUE,
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            created_at TEXT NOT NULL,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id)
        );

-- table: process_exec_events
CREATE TABLE process_exec_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        command_json TEXT NOT NULL,
        cwd TEXT NOT NULL,
        command_profile TEXT NOT NULL,
        decision TEXT NOT NULL,
        success INTEGER,
        exit_code INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: project_candidate_sets
CREATE TABLE project_candidate_sets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coordinator_project_uuid TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

-- table: project_candidates
CREATE TABLE project_candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            project_uuid TEXT NOT NULL,
            instance_uuid TEXT,
            root_path TEXT NOT NULL,
            project_role TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            manifest_hash TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            is_active_root INTEGER NOT NULL DEFAULT 0,
            scanned_at TEXT NOT NULL,
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id),
            UNIQUE(candidate_set_id, project_uuid)
        );

-- table: project_compatibility
CREATE TABLE project_compatibility(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            project_a_uuid TEXT NOT NULL,
            project_b_uuid TEXT NOT NULL,
            compatibility_status TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            human_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmed_by TEXT,
            confirmed_at TEXT,
            confirmation_reason TEXT,
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id),
            UNIQUE(candidate_set_id, project_a_uuid, project_b_uuid)
        );

-- table: project_component_mappings
CREATE TABLE project_component_mappings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            target_path TEXT,
            target_expected_hash TEXT,
            target_expected_absent INTEGER NOT NULL DEFAULT 0,
            action TEXT NOT NULL,
            rationale TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_result_json TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id),
            UNIQUE(consolidation_id, source_project_uuid, source_path)
        );

-- table: project_component_provenance
CREATE TABLE project_component_provenance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            mapping_id INTEGER NOT NULL,
            primary_project_uuid TEXT NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            target_path TEXT,
            target_before_hash TEXT,
            target_after_hash TEXT,
            backup_path TEXT,
            action TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            executed_by TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            rollback_status TEXT NOT NULL DEFAULT 'not_rolled_back',
            rolled_back_by TEXT,
            rolled_back_at TEXT,
            rollback_reason TEXT,
            UNIQUE(execution_id)
        );

-- table: project_consolidation_approvals
CREATE TABLE project_consolidation_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            approval_reason TEXT NOT NULL,
            human_confirmed INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id)
        );

-- table: project_consolidation_events
CREATE TABLE project_consolidation_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

-- table: project_consolidation_reviews
CREATE TABLE project_consolidation_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            reviewed_by TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            review_reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reviewed',
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id)
        );

-- table: project_consolidation_sources
CREATE TABLE project_consolidation_sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_root_path TEXT NOT NULL,
            source_manifest_hash TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            readonly_verified INTEGER NOT NULL DEFAULT 1,
            registered_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id),
            UNIQUE(consolidation_id, source_project_uuid)
        );

-- table: project_consolidations
CREATE TABLE project_consolidations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            coordinator_project_uuid TEXT NOT NULL,
            primary_project_uuid TEXT NOT NULL,
            primary_root_path TEXT NOT NULL,
            selection_hash TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            plan_revision INTEGER NOT NULL DEFAULT 1,
            plan_hash TEXT,
            approved_plan_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

-- table: project_findings
CREATE TABLE project_findings(
        id INTEGER PRIMARY KEY AUTOINCREMENT, finding_key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL, path TEXT, symbol TEXT, message TEXT NOT NULL,
        first_seen_task_id TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'active',
        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, project_uuid TEXT);

-- table: project_identity
CREATE TABLE project_identity(
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            project_uuid TEXT NOT NULL,
            origin_project_uuid TEXT,
            audit_project_id TEXT NOT NULL,
            identity_version INTEGER NOT NULL,
            identity_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

-- table: project_identity_events
CREATE TABLE project_identity_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT,
            instance_uuid TEXT,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

-- table: project_memory
CREATE TABLE project_memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, statement TEXT NOT NULL,
        source_path TEXT, source_hash TEXT, first_seen_task_id TEXT,
        last_confirmed_task_id TEXT, confidence REAL NOT NULL DEFAULT 1.0,
        evidence_hash TEXT, status TEXT NOT NULL DEFAULT 'active', supersedes_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, owner_scope TEXT NOT NULL DEFAULT 'project', sensitivity TEXT NOT NULL DEFAULT 'normal', consent_source TEXT, expires_at TEXT, revoked_at TEXT,
        FOREIGN KEY(supersedes_id) REFERENCES project_memory(id));

-- table: project_purpose
CREATE TABLE project_purpose(
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            project_uuid TEXT NOT NULL,
            purpose_json TEXT NOT NULL,
            purpose_hash TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

-- table: project_purpose_history
CREATE TABLE project_purpose_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT NOT NULL,
            purpose_json TEXT NOT NULL,
            purpose_hash TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

-- table: project_selection_events
CREATE TABLE project_selection_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

-- table: promoted_skills
CREATE TABLE promoted_skills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_key TEXT NOT NULL, version INTEGER NOT NULL,
        memory_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
        candidate_path TEXT NOT NULL, graduated_path TEXT,
        status TEXT NOT NULL DEFAULT 'candidate', content_hash TEXT NOT NULL,
        promoted_by TEXT NOT NULL, approved_by TEXT, approval_note TEXT,
        external_event_hash TEXT, supersedes_skill_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, graduated_at TEXT,
        revoked_at TEXT, revoke_reason TEXT, project_uuid TEXT,
        UNIQUE(skill_key,version),
        FOREIGN KEY(memory_id) REFERENCES project_memory(id),
        FOREIGN KEY(supersedes_skill_id) REFERENCES promoted_skills(id));

-- table: proxy_executions
CREATE TABLE proxy_executions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        capability TEXT NOT NULL,
        decision TEXT NOT NULL,
        success INTEGER,
        tool_call_id INTEGER,
        external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id)
    );

-- table: rag_retrieval_events
CREATE TABLE rag_retrieval_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, query_hash TEXT NOT NULL, backend TEXT NOT NULL,
        kinds_json TEXT NOT NULL, top_k INTEGER NOT NULL, result_count INTEGER NOT NULL,
        context_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: recovery_events
CREATE TABLE recovery_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
        status TEXT NOT NULL, details_json TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: resource_leases
CREATE TABLE resource_leases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_type TEXT NOT NULL,
        resource_key TEXT NOT NULL,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        lease_mode TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        heartbeat_at TEXT NOT NULL,
        released_at TEXT,
        base_hash TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}', expired_at TEXT, release_reason TEXT, overlap_warning_json TEXT, project_uuid TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: retention_runs
CREATE TABLE retention_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, deleted_count INTEGER NOT NULL,
        retained_count INTEGER NOT NULL, parameters_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: secret_resolver_approvals
CREATE TABLE secret_resolver_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT NOT NULL,
            scheme TEXT NOT NULL,
            provider_version TEXT NOT NULL,
            provider_hash TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('approved','revoked')),
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            revoked_by TEXT,
            revoked_at TEXT,
            UNIQUE(provider_id,provider_hash)
        );

-- table: secret_resolver_events
CREATE TABLE secret_resolver_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            provider_id TEXT,
            scheme TEXT,
            reference_hash TEXT,
            capability TEXT,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            governed_operation_id TEXT,
            external_event_hash TEXT
        );

-- table: session_revocations
CREATE TABLE session_revocations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, token_id TEXT NOT NULL,
        revoked_by TEXT NOT NULL, reason TEXT NOT NULL,
        external_event_hash TEXT, revoked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: session_tokens
CREATE TABLE session_tokens(
        token_hash TEXT PRIMARY KEY, token_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL, task_id TEXT NOT NULL,
        capability_set_json TEXT NOT NULL DEFAULT '[]',
        issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL, revoked_at TEXT,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: signed_state_index
CREATE TABLE signed_state_index(
        id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL,
        row_key TEXT NOT NULL, external_event_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(table_name,row_key,external_event_hash));

-- table: state_reconciliation_runs
CREATE TABLE state_reconciliation_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ok INTEGER NOT NULL,
        checked_rows INTEGER NOT NULL, unverifiable_rows INTEGER NOT NULL,
        details_json TEXT NOT NULL, latest_external_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- table: symbol_index
CREATE TABLE symbol_index(
        path TEXT NOT NULL,
        qualname TEXT NOT NULL,
        kind TEXT NOT NULL,
        line_start INTEGER NOT NULL,
        line_end INTEGER NOT NULL,
        signature TEXT NOT NULL,
        fingerprint TEXT NOT NULL, project_uuid TEXT,
        PRIMARY KEY(path, qualname)
    );

-- table: target_record_lineage
CREATE TABLE target_record_lineage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL,
            insert_run_id INTEGER NOT NULL,
            extraction_batch_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_record_token TEXT NOT NULL,
            source_record_token TEXT NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_locator_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            commit_receipt_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, key_id TEXT, source_key_id TEXT, target_key_id TEXT,
            UNIQUE(insert_run_id,source_record_token),
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id),
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );

-- table: target_schema_contracts
CREATE TABLE target_schema_contracts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_snapshot_id INTEGER NOT NULL,
            contract_version INTEGER NOT NULL,
            contract_schema_version INTEGER NOT NULL,
            contract_json TEXT NOT NULL,
            contract_hash TEXT NOT NULL,
            target_snapshot_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(target_snapshot_id) REFERENCES db_schema_snapshots(id),
            UNIQUE(consolidation_id, contract_version)
        );

-- table: task_handoffs
CREATE TABLE task_handoffs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        from_session_id TEXT NOT NULL,
        to_session_id TEXT NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: task_messages
CREATE TABLE task_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL UNIQUE, correlation_id TEXT NOT NULL,
        causation_id TEXT, task_id TEXT NOT NULL, from_session TEXT NOT NULL, to_session TEXT NOT NULL,
        kind TEXT NOT NULL, payload_json TEXT NOT NULL, payload_schema_version INTEGER NOT NULL,
        disclosure_level TEXT NOT NULL, artifact_refs_json TEXT NOT NULL, status TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: task_outcomes
CREATE TABLE task_outcomes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, outcome TEXT NOT NULL, rated_by TEXT NOT NULL,
        test_pass_rate REAL, rework_count INTEGER NOT NULL DEFAULT 0, note TEXT, benchmark_key TEXT, task_category TEXT,
        agent_id TEXT, model_id TEXT, policy_revision TEXT, context_revision TEXT, retrieval_backend TEXT, repository_revision TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: task_plans
CREATE TABLE task_plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, revision INTEGER NOT NULL,
        status TEXT NOT NULL, plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL,
        submitted_by TEXT NOT NULL, approved_by TEXT, approval_note TEXT,
        submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, approved_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id), UNIQUE(task_id,revision));

-- table: task_reclaims
CREATE TABLE task_reclaims(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        old_owner_session_id TEXT, new_owner_session_id TEXT,
        requested_by_session_id TEXT NOT NULL, reason TEXT NOT NULL,
        status TEXT NOT NULL, requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT, FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: task_role_assignments
CREATE TABLE task_role_assignments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, session_id TEXT NOT NULL, token_id TEXT NOT NULL,
        role TEXT NOT NULL, permissions_json TEXT NOT NULL, assigned_by TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(task_id) REFERENCES tasks(id));

-- table: tasks
CREATE TABLE tasks(
        id TEXT PRIMARY KEY,
        request TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0,
        approved_scope TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , owner_session_id TEXT, task_state TEXT NOT NULL DEFAULT 'ready', last_heartbeat TEXT, stale_at TEXT, reclaim_status TEXT, reclaim_requested_by TEXT);

-- table: tool_calls
CREATE TABLE tool_calls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        classification TEXT NOT NULL,
        input_json TEXT NOT NULL,
        success INTEGER NOT NULL,
        output_summary TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: tool_events
CREATE TABLE tool_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        classification_json TEXT NOT NULL,
        args_hash TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        success INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- table: workflow_steps
CREATE TABLE workflow_steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        workflow_name TEXT NOT NULL,
        step_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        skip_reason TEXT,
        note TEXT,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completion_source TEXT NOT NULL DEFAULT 'none', evidence_type TEXT, evidence_id TEXT, result_hash TEXT, command_name TEXT, exit_code INTEGER, verification_status TEXT NOT NULL DEFAULT 'unverified', external_event_hash TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        UNIQUE(task_id, workflow_name, step_name)
    );

-- table: write_audit
CREATE TABLE write_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        target TEXT NOT NULL,
        allowed INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );

-- index: idx_async_jobs_task_state
CREATE INDEX idx_async_jobs_task_state ON async_jobs(task_id,state,created_at);

-- index: idx_authenticated_requests_token
CREATE INDEX idx_authenticated_requests_token ON authenticated_requests(token_id,sequence);

-- index: idx_claim_evidence_claim_id
CREATE INDEX idx_claim_evidence_claim_id ON claim_evidence(claim_id);

-- index: idx_claims_task_id
CREATE INDEX idx_claims_task_id ON claims(task_id);

-- index: idx_context_budget_profile
CREATE INDEX idx_context_budget_profile
            ON context_budget_decisions(model_profile,created_at);

-- index: idx_context_budget_task
CREATE INDEX idx_context_budget_task
            ON context_budget_decisions(task_id,transport_revision,created_at);

-- index: idx_context_compression_compare_task
CREATE INDEX idx_context_compression_compare_task
            ON context_compression_comparisons(task_id,created_at);

-- index: idx_context_compression_eval_task
CREATE INDEX idx_context_compression_eval_task
            ON context_compression_evaluation_runs(task_id,created_at);

-- index: idx_context_expansion_pack
CREATE INDEX idx_context_expansion_pack
            ON context_expansion_events(transport_pack_id,created_at);

-- index: idx_context_expansion_session_task
CREATE INDEX idx_context_expansion_session_task
            ON context_expansion_sessions(task_id,transport_pack_id,created_at);

-- index: idx_context_knowledge_task
CREATE INDEX idx_context_knowledge_task ON context_knowledge_events(task_id,created_at);

-- index: idx_context_packs_task
CREATE INDEX idx_context_packs_task ON context_packs(task_id,status,revision);

-- index: idx_context_profile_snapshot_name
CREATE INDEX idx_context_profile_snapshot_name
            ON context_model_profile_snapshots(profile_name,created_at);

-- index: idx_context_requirement_task
CREATE INDEX idx_context_requirement_task
            ON context_requirement_ledger(task_id,context_revision,kind,ordinal);

-- index: idx_context_token_observation_profile
CREATE INDEX idx_context_token_observation_profile
            ON context_token_observations(model_profile,tokenizer_id,created_at);

-- index: idx_context_token_observation_task
CREATE INDEX idx_context_token_observation_task
            ON context_token_observations(task_id,created_at);

-- index: idx_context_transport_eval_task
CREATE INDEX idx_context_transport_eval_task
            ON context_transport_evaluations(task_id,created_at);

-- index: idx_context_transport_task
CREATE INDEX idx_context_transport_task
            ON context_transport_packs(task_id,status,transport_revision);

-- index: idx_coordination_events_task
CREATE INDEX idx_coordination_events_task ON coordination_events(task_id,created_at);

-- index: idx_db_connections_role_domain
CREATE INDEX idx_db_connections_role_domain
            ON db_connections(role, domain_id, status);

-- index: idx_db_consolidation_sources
CREATE INDEX idx_db_consolidation_sources
            ON db_consolidation_sources(consolidation_id, source_connection_id);

-- index: idx_db_consolidations_target
CREATE INDEX idx_db_consolidations_target
            ON db_consolidations(target_connection_id, status);

-- index: idx_db_extraction_batches_plan
CREATE INDEX idx_db_extraction_batches_plan
            ON db_extraction_batches(consolidation_id, source_connection_id, target_contract_id, status);

-- index: idx_db_extraction_events_batch
CREATE INDEX idx_db_extraction_events_batch
            ON db_extraction_events(batch_id, created_at);

-- index: idx_db_field_mappings_plan
CREATE INDEX idx_db_field_mappings_plan
            ON db_field_mappings(consolidation_id, target_contract_id, source_connection_id, status);

-- index: idx_db_reconciliation_findings_run
CREATE INDEX idx_db_reconciliation_findings_run
            ON db_reconciliation_findings(reconciliation_run_id,severity);

-- index: idx_db_reconciliation_insert
CREATE INDEX idx_db_reconciliation_insert
            ON db_reconciliation_runs(insert_run_id,status,id);

-- index: idx_db_recovery_cases_status
CREATE INDEX idx_db_recovery_cases_status
            ON db_recovery_cases(status,case_type,insert_run_id);

-- index: idx_db_recovery_checkpoints_insert
CREATE INDEX idx_db_recovery_checkpoints_insert
            ON db_recovery_checkpoints(insert_run_id,reconciliation_run_id,id);

-- index: idx_db_schema_snapshots_connection
CREATE INDEX idx_db_schema_snapshots_connection
            ON db_schema_snapshots(connection_id, status, captured_at);

-- index: idx_db_target_insert_events_run
CREATE INDEX idx_db_target_insert_events_run
            ON db_target_insert_events(insert_run_id,created_at);

-- index: idx_db_target_insert_runs_status
CREATE INDEX idx_db_target_insert_runs_status
            ON db_target_insert_runs(consolidation_id,target_connection_id,status);

-- index: idx_db_validation_findings_batch
CREATE INDEX idx_db_validation_findings_batch
            ON db_validation_findings(batch_id, row_ordinal, severity);

-- index: idx_egress_events_task_id
CREATE INDEX idx_egress_events_task_id ON egress_events(task_id);

-- index: idx_erasure_events_plan
CREATE INDEX idx_erasure_events_plan ON data_subject_erasure_events(plan_id,event_type);

-- index: idx_erasure_requests_entity
CREATE INDEX idx_erasure_requests_entity ON data_subject_erasure_requests(canonical_entity_id,created_at);

-- index: idx_erasure_requests_locator
CREATE INDEX idx_erasure_requests_locator
            ON data_subject_erasure_requests(entity_locator_hash,created_at);

-- index: idx_evaluation_runs_dimensions
CREATE INDEX idx_evaluation_runs_dimensions ON evaluation_runs(agent_name,model_name,policy_version,created_at);

-- index: idx_evolution_proposals_status
CREATE INDEX idx_evolution_proposals_status ON evolution_proposals(status,created_at);

-- index: idx_execution_manifests_task
CREATE INDEX idx_execution_manifests_task ON execution_manifests(task_id,created_at);

-- index: idx_file_read_cache_task_id
CREATE INDEX idx_file_read_cache_task_id ON file_read_cache(task_id);

-- index: idx_file_versions_path
CREATE INDEX idx_file_versions_path ON file_versions(path,version);

-- index: idx_governance_baseline_file
CREATE INDEX idx_governance_baseline_file ON governance_baseline(file_path);

-- index: idx_governance_change_ack
CREATE INDEX idx_governance_change_ack ON governance_change_log(acknowledged);

-- index: idx_governed_operations_task
CREATE INDEX idx_governed_operations_task ON governed_operations(task_id,session_id,status,started_at);

-- index: idx_guarded_executions_task_id
CREATE INDEX idx_guarded_executions_task_id ON guarded_executions(task_id);

-- index: idx_identity_bindings_exact
CREATE INDEX idx_identity_bindings_exact
            ON identity_bindings(exact_key_fingerprint);

-- index: idx_identity_bindings_strong
CREATE INDEX idx_identity_bindings_strong
            ON identity_bindings(strong_fingerprint);

-- index: idx_identity_candidates_run
CREATE INDEX idx_identity_candidates_run
            ON identity_candidates(resolution_run_id,status);

-- index: idx_job_events_job
CREATE INDEX idx_job_events_job ON job_events(job_id,created_at);

-- index: idx_knowledge_edges_from
CREATE INDEX idx_knowledge_edges_from ON knowledge_edges(from_node_id,relation,status);

-- index: idx_knowledge_edges_to
CREATE INDEX idx_knowledge_edges_to ON knowledge_edges(to_node_id,relation,status);

-- index: idx_knowledge_embeddings_backend
CREATE INDEX idx_knowledge_embeddings_backend ON knowledge_embeddings(backend,source_kind);

-- index: idx_knowledge_nodes_type
CREATE INDEX idx_knowledge_nodes_type ON knowledge_nodes(node_type,status);

-- index: idx_knowledge_retrieval_backend
CREATE INDEX idx_knowledge_retrieval_backend ON knowledge_retrieval_events(backend,created_at);

-- index: idx_lineage_one_active
CREATE UNIQUE INDEX idx_lineage_one_active
            ON lineage_keys(status) WHERE status='active';

-- index: idx_primary_project_selected
CREATE INDEX idx_primary_project_selected
            ON primary_project_selections(primary_project_uuid, selected_at);

-- index: idx_process_exec_events_task
CREATE INDEX idx_process_exec_events_task ON process_exec_events(task_id);

-- index: idx_project_candidates_set
CREATE INDEX idx_project_candidates_set
            ON project_candidates(candidate_set_id, project_uuid);

-- index: idx_project_compatibility_set
CREATE INDEX idx_project_compatibility_set
            ON project_compatibility(candidate_set_id, compatibility_status);

-- index: idx_project_component_mappings
CREATE INDEX idx_project_component_mappings
            ON project_component_mappings(consolidation_id, status, action);

-- index: idx_project_component_provenance_target
CREATE INDEX idx_project_component_provenance_target
            ON project_component_provenance(primary_project_uuid, target_path, executed_at);

-- index: idx_project_consolidation_sources
CREATE INDEX idx_project_consolidation_sources
            ON project_consolidation_sources(consolidation_id, source_project_uuid);

-- index: idx_project_consolidations_candidate
CREATE INDEX idx_project_consolidations_candidate
            ON project_consolidations(candidate_set_id, status);

-- index: idx_project_findings_lookup
CREATE INDEX idx_project_findings_lookup ON project_findings(kind,status,occurrences);

-- index: idx_project_findings_project_uuid
CREATE INDEX "idx_project_findings_project_uuid" ON "project_findings"(project_uuid);

-- index: idx_project_identity_events_project
CREATE INDEX idx_project_identity_events_project
            ON project_identity_events(project_uuid, created_at);

-- index: idx_project_memory_query
CREATE INDEX idx_project_memory_query ON project_memory(kind,status,confidence);

-- index: idx_project_memory_scope
CREATE INDEX idx_project_memory_scope ON project_memory(owner_scope,status,created_at);

-- index: idx_promoted_skills_project_uuid
CREATE INDEX "idx_promoted_skills_project_uuid" ON "promoted_skills"(project_uuid);

-- index: idx_promoted_skills_status
CREATE INDEX idx_promoted_skills_status ON promoted_skills(status,skill_key,version);

-- index: idx_proxy_executions_task
CREATE INDEX idx_proxy_executions_task ON proxy_executions(task_id);

-- index: idx_resource_leases_project_uuid
CREATE INDEX "idx_resource_leases_project_uuid" ON "resource_leases"(project_uuid);

-- index: idx_resource_leases_resource
CREATE INDEX idx_resource_leases_resource ON resource_leases(resource_type,resource_key,status);

-- index: idx_resource_leases_task
CREATE INDEX idx_resource_leases_task ON resource_leases(task_id,status);

-- index: idx_secret_resolver_approvals_scheme
CREATE INDEX idx_secret_resolver_approvals_scheme
            ON secret_resolver_approvals(scheme,status);

-- index: idx_signed_state_lookup
CREATE INDEX idx_signed_state_lookup ON signed_state_index(table_name,row_key);

-- index: idx_symbol_index_project_uuid
CREATE INDEX "idx_symbol_index_project_uuid" ON "symbol_index"(project_uuid);

-- index: idx_target_record_lineage_entity
CREATE INDEX idx_target_record_lineage_entity
            ON target_record_lineage(canonical_entity_id,insert_run_id);

-- index: idx_target_schema_contracts_consolidation
CREATE INDEX idx_target_schema_contracts_consolidation
            ON target_schema_contracts(consolidation_id, status, contract_version);

-- index: idx_task_messages_route
CREATE INDEX idx_task_messages_route ON task_messages(task_id,to_session,created_at);

-- index: idx_task_outcomes_cohort
CREATE INDEX idx_task_outcomes_cohort ON task_outcomes(task_category,agent_id,model_id,policy_revision,created_at);

-- index: idx_task_plans_active
CREATE INDEX idx_task_plans_active ON task_plans(task_id,status,revision);

-- index: idx_task_roles_active
CREATE INDEX idx_task_roles_active ON task_role_assignments(task_id,session_id,status);

-- index: idx_tool_calls_task_id
CREATE INDEX idx_tool_calls_task_id ON tool_calls(task_id);

-- index: idx_tool_events_task_id
CREATE INDEX idx_tool_events_task_id ON tool_events(task_id);

-- index: idx_workflow_steps_task_id
CREATE INDEX idx_workflow_steps_task_id ON workflow_steps(task_id);

-- trigger: trg_erasure_plan_immutable_delete
CREATE TRIGGER trg_erasure_plan_immutable_delete
        BEFORE DELETE ON data_subject_erasure_plans
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_plan'); END;

-- trigger: trg_erasure_plan_immutable_update
CREATE TRIGGER trg_erasure_plan_immutable_update
        BEFORE UPDATE ON data_subject_erasure_plans
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_plan'); END;

-- trigger: trg_erasure_request_immutable_delete
CREATE TRIGGER trg_erasure_request_immutable_delete
        BEFORE DELETE ON data_subject_erasure_requests
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_request'); END;

-- trigger: trg_erasure_request_immutable_update
CREATE TRIGGER trg_erasure_request_immutable_update
        BEFORE UPDATE ON data_subject_erasure_requests
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_request'); END;
