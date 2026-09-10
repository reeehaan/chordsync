import 'dart:convert';

import 'package:flutter/services.dart';

import 'shared_timeline.dart';

class SharedTimelineAssetLoader {
  static const assetPath =
      'assets/practice_timeline/synthetic_shared_timeline.json';

  static Future<SharedTimeline> load({AssetBundle? bundle}) async {
    final jsonText = await (bundle ?? rootBundle).loadString(assetPath);
    final json = jsonDecode(jsonText) as Map<String, dynamic>;
    return SharedTimeline.fromJson(json);
  }
}
