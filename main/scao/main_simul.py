
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--cpu', action='store_true')
parser.add_argument('--overrides', type=str)
parser.add_argument('yml_file', nargs='+', type=str, help='YAML parameter files')

if __name__ == '__main__':
    args = parser.parse_args()
    target_device_idx = 0
    if args.cpu:
        target_device_idx = -1

    import specula
    specula.init(target_device_idx, precision=1)

    print(args)    
    from specula.simul import Simul
    simul = Simul(*args.yml_file, overrides=args.overrides)
    simul.run()