def binary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1

if __name__ == '__main__':
    test_array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print(f'Index of 7: {binary_search(test_array, 7)}')
    print(f'Index of 1: {binary_search(test_array, 1)}')
    print(f'Index of 10: {binary_search(test_array, 10)}')
    print(f'Index of 11: {binary_search(test_array, 11)}')
