from analysis.temporal.models import (
    Bar,
    TimelineEvent,
)


def group_into_bars(
    events: list[TimelineEvent],
) -> list[Bar]:
    if not events:
        return []

    bars = []
    current_beats = []
    bar_number = 1

    for event in events:
        if event.is_downbeat and current_beats:
            bars.append(
                Bar(
                    bar_number=bar_number,
                    start_time=current_beats[0].time,
                    end_time=event.time,
                    beats=current_beats,
                )
            )

            bar_number += 1
            current_beats = []

        current_beats.append(event)

    if current_beats:
        bars.append(
            Bar(
                bar_number=bar_number,
                start_time=current_beats[0].time,
                end_time=current_beats[-1].time,
                beats=current_beats,
            )
        )

    return bars
