# Shared fixtures; case bodies live in top/ and mid/. See TESTS.md.
"""Bounded exact-input history and owner-scoped release on real stores."""
from datetime import timedelta
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from mycel._activity import AppliedMutation, ClassificationReference, MutationActivity
from mycel._classification_store import ClassificationStore
from mycel._collection import CollectionStore
from mycel._derive import DeriveStore
from mycel._errors import MycelError
from mycel._evidence import EvidenceStore, snapshot
from mycel._locks import atomic_transaction, invocation_guard, operation_guard, removal_guard
from mycel._verification import ConfirmationStore
from mycel._source_refs import parse_source_address
try:
    from .test_classification_store import ClassificationStoreFixture, NOW, AT
except ImportError:
    from test_classification_store import ClassificationStoreFixture, NOW, AT

from contextlib import ExitStack
from copy import deepcopy

from mycel._classification_payload import DecisionPayload, EvidenceBundle
from mycel._drift_retention import DriftHistoryStore
from mycel._drift_store import DriftStore
from mycel._evidence import snapshot
from mycel._locks import operation_guard

try:
    from .test_classification_store import AT, ClassificationStoreFixture
except ImportError:
    from test_classification_store import AT, ClassificationStoreFixture


class DriftRetentionStoreTests(ClassificationStoreFixture):
    check_kind = "store"

    def guarded(self, connection):
        stack = ExitStack()
        for name in sorted(self.base.settings.values['repos']):
            stack.enter_context(operation_guard(connection, name, 'pass'))
        return stack

    def row(self, connection, identifier):
        return connection.execute('SELECT id,repository,dependant_version,opened_at,closed_at,state,evidence_owner '
            'FROM public.mycel_drifts WHERE id=%s', (identifier,)).fetchone()

    def seed_history(self, connection, prepared, count, *, first_id=None, at=AT):
        """Distinct valid canonical request policies, with stand-in closed stages.

        Capture texts/baselines come from the real public producer. Only model
        routing identities and historical stage replies are deterministic data.
        """
        row = self.row(connection, prepared.drift_id)
        source = next(item for item in row[5]['sources'] if item['id'] == prepared.reason_id)
        request = row[5]['classificationRequests'][prepared.input_hash]
        histories = []
        for number in range(count):
            payload = prepared.decision.as_dict()
            payload['routing']['revision'] = 'fixture-history-' + str(number)
            decision = DecisionPayload(payload)
            bundle_payload = deepcopy(request['bundle'])
            bundle_payload.update(inputHash=decision.input_hash, requestSnapshot='snapshot:' + decision.input_hash,
                                  disposition='obsolete')
            bundle = EvidenceBundle(bundle_payload)
            DriftStore(connection)._retain(row[1], row[6],
                (snapshot(decision.canonical_bytes), snapshot(bundle.canonical_bytes)))
            state = deepcopy(row[5])
            answered = deepcopy(source)
            answered['classification'] = {'status': 'complete', 'pairHash': source['pairHash'],
                'inputHash': decision.input_hash, 'judgement': 'needs_review',
                'evidence': {'stage': 'fixture'}}
            state['classificationRequests'] = {decision.input_hash: {**deepcopy(request),
                'payloadSnapshot': 'snapshot:' + decision.input_hash, 'bundle': bundle_payload,
                'bundleSnapshot': 'snapshot:' + bundle.evidence_hash}}
            state['history'] = [{'at': at, 'source': source['id'], 'pairHash': source['pairHash'],
                'inputHash': decision.input_hash, 'status': 'complete', 'judgement': 'needs_review',
                'evidence': {'stage': 'fixture'}, 'obsolete': True}]
            identifier = DriftHistoryStore(connection).archive_source_in_transaction(row, answered, state, at=at)
            if number == 0 and first_id is not None:
                # Fixed UUID permits an exact tie-order assertion while the
                # producer still created the complete owning record/refs.
                old_owner = self.row(connection, identifier)[6]
                connection.execute('UPDATE public.mycel_drifts SET id=%s WHERE id=%s', (first_id, identifier))
                connection.execute('UPDATE public.mycel_evidence_owners SET identity=%s WHERE id=%s',
                                    (str(first_id), old_owner))
                identifier = str(first_id)
            histories.append((identifier, decision.input_hash, bundle.evidence_hash))
        DriftHistoryStore(connection).retain_live_references_in_transaction(row, row[5])
        return histories


# Archived complete imports; restore needed names in their original scope, not at this file tail.
