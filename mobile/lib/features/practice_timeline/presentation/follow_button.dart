import 'package:flutter/material.dart';

/// The "Follow" button shown once the user scrolls a chart or lyric sheet away
/// from the playing position. One look for both, so they never drift apart.
class FollowButton extends StatelessWidget {
  const FollowButton({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton.tonal(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 38),
        padding: const EdgeInsets.symmetric(horizontal: 20),
      ),
      child: const Text('Follow'),
    );
  }
}
