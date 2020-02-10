
class State:
    """For (de)serializing S.State."""

    def __init__(self, serialized=''):
        parts = {}
        if serialized.startswith('State(') and serialized.endswith(')'):
            parts = dict([
                part.split('=')
                for part in serialized[6:-1].split(',')
                if part
            ])
        self.playing = parts.get('playing')
        self.state = parts.get('state', 'std')
        self.color = parts.get('color', 'brownish')
        self.rnd = parts.get('rnd', 0)

    def goto(self, state):
        """Sets a new state."""
        self.state = state

    def play(self, what):
        """Stops if `what=None`."""
        self.playing = what

    def __repr__(self):
        parts = [
            '{}={}'.format(k, v)
            for k, v in dict(
                playing=self.playing,
                state=self.state,
                color=self.color,
                rnd=self.rnd,
            ).items()
            if v is not None
        ]
        return 'State({})'.format(','.join(parts))
