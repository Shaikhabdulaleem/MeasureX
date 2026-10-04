import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;
import 'package:measurex/src/core/api_client.dart';

/// Unit tests for the M4 Team-Leader API client methods, using a mocked
/// http.Client so no server is needed. They assert the request shape (path,
/// method, body, auth header) and that responses parse into the models the
/// Team-Leader screens render.
void main() {
  group('ApiClient — Team Leader tools', () {
    test('correctPackage POSTs dimensions + reason and parses the package',
        () async {
      late http.Request captured;
      final api = ApiClient(
        client: MockClient((req) async {
          captured = req;
          return http.Response(
            jsonEncode({
              'id': 'pkg-1',
              'shipmentId': 'ship-1',
              'status': 'active',
              'packageNumber': 2,
              'currentVersion': {
                'versionNo': 2,
                'lengthMm': 500,
                'widthMm': 400,
                'heightMm': 300,
                'billingLCm': 50,
                'billingWCm': 40,
                'billingHCm': 30,
                'cbm': 0.06,
                'volumetricG': 12000,
                'chargeableG': 12000,
                'divisorUsed': 5000,
                'method': 'manual',
              },
            }),
            201,
          );
        }),
      );

      final pkg = await api.correctPackage(
        'tok',
        'pkg-1',
        lengthMm: 500,
        widthMm: 400,
        heightMm: 300,
        reason: 'mismeasured',
      );

      expect(captured.method, 'POST');
      expect(captured.url.path, endsWith('/packages/pkg-1/corrections'));
      expect(captured.headers['Authorization'], 'Bearer tok');
      final body = jsonDecode(captured.body) as Map<String, dynamic>;
      expect(body['lengthMm'], 500);
      expect(body['reason'], 'mismeasured');
      expect(pkg.currentVersion!.billingLCm, 50);
      expect(pkg.currentVersion!.chargeableG, 12000);
    });

    test('reopenShipment POSTs a reason and parses the shipment', () async {
      late http.Request captured;
      final api = ApiClient(
        client: MockClient((req) async {
          captured = req;
          return http.Response(
            jsonEncode({
              'id': 's1',
              'awb': 'AY12345678901',
              'status': 'in_progress',
              'totals': {}
            }),
            200,
          );
        }),
      );

      final s = await api.reopenShipment('tok', 'AY12345678901', 'add a piece');
      expect(captured.url.path, endsWith('/shipments/AY12345678901/reopen'));
      expect((jsonDecode(captured.body) as Map<String, dynamic>)['reason'],
          'add a piece');
      expect(s.status, 'in_progress');
    });

    test('listFlags parses the review queue', () async {
      final api = ApiClient(
        client: MockClient((req) async {
          expect(req.url.queryParameters['status'], 'open');
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'id': 'f1',
                  'type': 'worker_flag',
                  'status': 'open',
                  'shipmentId': 's1',
                  'awb': 'AY12345678901',
                  'note': 'looks squashed',
                },
              ],
              'nextCursor': null,
            }),
            200,
          );
        }),
      );

      final flags = await api.listFlags('tok');
      expect(flags, hasLength(1));
      expect(flags.first.type, 'worker_flag');
      expect(flags.first.awb, 'AY12345678901');
    });

    test('listRemeasurements parses open requests', () async {
      final api = ApiClient(
        client: MockClient((req) async {
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'id': 'r1',
                  'shipmentId': 's1',
                  'reason': 'customer_dispute',
                  'status': 'open',
                  'packageIds': ['p1'],
                  'awb': 'AY12345678901',
                },
              ],
              'nextCursor': null,
            }),
            200,
          );
        }),
      );

      final reqs = await api.listRemeasurements('tok');
      expect(reqs, hasLength(1));
      expect(reqs.first.reason, 'customer_dispute');
      expect(reqs.first.packageIds, ['p1']);
    });

    test('resolveFlag and cancelRemeasure surface API errors', () async {
      final api = ApiClient(
        client: MockClient((req) async {
          return http.Response(
              jsonEncode({'code': 'FLAG_NOT_OPEN', 'message': 'nope'}), 409);
        }),
      );
      expect(
        () => api.resolveFlag('tok', 'f1', 'approve'),
        throwsA(
            isA<ApiException>().having((e) => e.code, 'code', 'FLAG_NOT_OPEN')),
      );
    });
  });
}
